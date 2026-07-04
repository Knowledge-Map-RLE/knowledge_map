"""Compare pipeline output against manually-created ground truth triplets.

Usage:
    python -m pytest tests/articles/ -v
    python -m pytest tests/articles/test_pipeline_vs_ground_truth.py -v --coverage
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import grpc
import pytest

from src import knowledge_language_pb2_grpc, knowledge_language_pb2
from tests.articles.conftest import (
    load_article_text,
    split_sentences,
    parse_truth_file,
    find_matching_statement,
    GROUND_TRUTH,
    is_uuid,
    GroundTruthEntry,
)

pytestmark = pytest.mark.e2e

CORE_HOST = "localhost"
CORE_PORT = 50056

logger = logging.getLogger(__name__)


def _channel() -> grpc.aio.Channel:
    return grpc.aio.insecure_channel(
        f"{CORE_HOST}:{CORE_PORT}",
        options=[
            ("grpc.max_send_message_length", 256 * 1024 * 1024),
            ("grpc.max_receive_message_length", 256 * 1024 * 1024),
        ],
    )


@pytest.fixture(scope="module")
def event_loop():
    import asyncio
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


async def _get_article_results(stub, text: str, doc_id: str):
    """Run pipeline on article text sentence by sentence."""
    import asyncio
    sentences = split_sentences(text)
    responses = []
    for i, sent in enumerate(sentences):
        try:
            resp = await asyncio.wait_for(
                stub.ProcessText(
                    knowledge_language_pb2.ProcessTextRequest(
                        text=sent,
                        doc_id=f"{doc_id}-sent-{i:04d}",
                        use_llm=False,
                    ),
                ),
                timeout=30,
            )
            responses.append(resp)
        except Exception as e:
            responses.append(None)
    return responses, sentences


def _resolve_lookup(entries: list) -> dict:
    lookup = {}
    for e in entries:
        lookup[e.uuid] = e
    return lookup


def _find_matches(
    entries: list[GroundTruthEntry],
    responses: list,
) -> tuple[list[str], list[str], int, int, int, int]:
    lookup = _resolve_lookup(entries)
    fact_matched, fact_total = 0, 0
    meta_matched, meta_total = 0, 0
    matched = []
    missed = []
    for entry in entries:
        if entry.is_fact:
            fact_total += 1
        else:
            meta_total += 1
        triplet = entry.resolved_triplet(lookup)
        if find_matching_statement(
            triplet, responses,
            is_meta=not entry.is_fact,
            gt_entry=entry,
            lookup=lookup,
        ):
            matched.append(entry.uuid)
            if entry.is_fact:
                fact_matched += 1
            else:
                meta_matched += 1
        else:
            missed.append((entry.uuid, entry.subject, entry.predicate, entry.object))
    return matched, missed, fact_matched, fact_total, meta_matched, meta_total


@pytest.mark.asyncio
async def test_abstract_against_pipeline():
    """Compare Abstract ground truth against pipeline output."""
    gtdir = GROUND_TRUTH / "hallmarks_of_pd"
    truth_files = sorted(gtdir.glob("*.truth"))

    if not truth_files:
        pytest.skip("No ground truth files found")

    text = load_article_text("the hallmarks of parkinsons disease")
    sentences = split_sentences(text)

    async with _channel() as channel:
        stub = knowledge_language_pb2_grpc.KnowledgeLanguageServiceStub(channel)
        responses = []
        for i, sent in enumerate(sentences):
            try:
                resp = await asyncio.wait_for(
                    stub.ProcessText(
                        knowledge_language_pb2.ProcessTextRequest(
                            text=sent,
                            doc_id=f"hallmarks_of_pd-sent-{i:04d}",
                            use_llm=False,
                        ),
                    ),
                    timeout=30,
                )
                responses.append(resp)
            except Exception as e:
                responses.append(None)

    total_matched = 0
    total_missed = 0
    total_fact_matched = 0
    total_fact_total = 0
    total_meta_matched = 0
    total_meta_total = 0
    all_missed: list = []

    for tf in truth_files:
        entries_by_sent = parse_truth_file(tf)
        for sent_text, entries in entries_by_sent.items():
            sent_responses = [
                r for r, s in zip(responses, sentences)
                if s.strip().startswith(sent_text[:50])
            ]
            if not sent_responses:
                sent_responses = [
                    r for r, s in zip(responses, sentences)
                    if s.strip() == sent_text.strip()
                ]
            if all(r is None for r in sent_responses):
                sent_responses = [r for r in responses if r is not None]

            matched, missed, fact_m, fact_t, meta_m, meta_t = _find_matches(entries, sent_responses)
            total_matched += len(matched)
            total_missed += len(missed)
            total_fact_matched += fact_m
            total_fact_total += fact_t
            total_meta_matched += meta_m
            total_meta_total += meta_t
            for item in missed:
                all_missed.append((sent_text[:60], item))

    total = total_matched + total_missed
    coverage = total_matched / total * 100 if total > 0 else 0
    fact_cov = total_fact_matched / total_fact_total * 100 if total_fact_total > 0 else 0
    meta_cov = total_meta_matched / total_meta_total * 100 if total_meta_total > 0 else 0

    print(f"\n{'='*60}")
    print(f"ALL: {total_matched}/{total} ({coverage:.1f}%)")
    print(f"FACT: {total_fact_matched}/{total_fact_total} ({fact_cov:.1f}%)")
    print(f"META: {total_meta_matched}/{total_meta_total} ({meta_cov:.1f}%)")
    print(f"{'='*60}")

    if all_missed:
        print(f"\nMISSED TRIPLETS ({len(all_missed)}):")
        for sent_preview, (uuid_val, subj, pred, obj) in all_missed:
            print(f"  [{uuid_val[:12]}...] {subj} -> {pred} -> {obj}")
            print(f"    Sentence: {sent_preview}...")

    assert coverage >= 1, f"Coverage too low: {coverage:.1f}%"

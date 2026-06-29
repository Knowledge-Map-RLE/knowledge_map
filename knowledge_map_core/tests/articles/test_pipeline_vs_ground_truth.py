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


def _find_matches(entries: list, responses: list) -> tuple[list[str], list[str]]:
    lookup = _resolve_lookup(entries)
    matched = []
    missed = []
    for entry in entries:
        triplet = entry.resolved_triplet(lookup)
        if find_matching_statement(triplet, responses):
            matched.append(entry.uuid)
        else:
            missed.append((entry.uuid, entry.subject, entry.predicate, entry.object))
    return matched, missed


@pytest.mark.asyncio
async def test_abstract_against_pipeline():
    """Compare Abstract ground truth against pipeline output."""
    gtdir = GROUND_TRUTH / "hallmarks_of_pd"
    truth_files = sorted(gtdir.glob("*.truth"))

    if not truth_files:
        pytest.skip("No ground truth files found")

    text = load_article_text("the hallmarks of parkinsons disease")
    # Limit to first 30 sentences for quick iteration
    sentences = split_sentences(text)[:30]

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
    all_missed = []

    for tf in truth_files:
        entries_by_sent = parse_truth_file(tf)
        for sent_text, entries in entries_by_sent.items():
            sent_responses = [
                r for r, s in zip(responses, sentences)
                if s.strip().startswith(sent_text[:50])  # fuzzy match by prefix
            ]
            if not sent_responses:
                # Try exact match
                sent_responses = [
                    r for r, s in zip(responses, sentences)
                    if s.strip() == sent_text.strip()
                ]
            if all(r is None for r in sent_responses):
                sent_responses = [r for r in responses if r is not None]

            matched, missed = _find_matches(entries, sent_responses)
            total_matched += len(matched)
            total_missed += len(missed)
            for item in missed:
                all_missed.append((sent_text[:60], item))

    total = total_matched + total_missed
    coverage = total_matched / total * 100 if total > 0 else 0

    print(f"\n{'='*60}")
    print(f"GROUND TRUTH COVERAGE: {total_matched}/{total} ({coverage:.1f}%)")
    print(f"{'='*60}")

    if all_missed:
        print(f"\nMISSED TRIPLETS ({len(all_missed)}):")
        for sent_preview, (uuid_val, subj, pred, obj) in all_missed:
            print(f"  [{uuid_val[:12]}...] {subj} -> {pred} -> {obj}")
            print(f"    Sentence: {sent_preview}...")

    assert coverage >= 1, f"Coverage too low: {coverage:.1f}%"

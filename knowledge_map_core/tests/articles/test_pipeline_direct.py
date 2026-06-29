"""Compare pipeline output against ground truth (direct, no gRPC)."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import pytest

from src.services.pipeline import Pipeline
from tests.articles.conftest import (
    load_article_text,
    split_sentences,
    parse_truth_file,
    find_matching_statement,
    GROUND_TRUTH,
)

pytestmark = pytest.mark.e2e

logger = logging.getLogger(__name__)


def _resolve_lookup(entries: list) -> dict:
    lookup = {}
    for e in entries:
        lookup[e.uuid] = e
    return lookup


def _find_matches(entries: list, responses: list) -> tuple[list[tuple], list[tuple]]:
    lookup = _resolve_lookup(entries)
    matched = []
    missed = []
    for entry in entries:
        triplet = entry.resolved_triplet(lookup)
        if find_matching_statement(triplet, responses):
            matched.append((entry.uuid, entry.subject, entry.predicate, entry.object))
        else:
            missed.append((entry.uuid, entry.subject, entry.predicate, entry.object))
    return matched, missed


@pytest.mark.asyncio
async def test_abstract_against_pipeline():
    """Compare Abstract ground truth against pipeline output (direct call)."""
    gtdir = GROUND_TRUTH / "hallmarks_of_pd"
    truth_files = sorted(gtdir.glob("*.truth"))

    if not truth_files:
        pytest.skip("No ground truth files found")

    text = load_article_text("the hallmarks of parkinsons disease")
    sentences = split_sentences(text)[:222]

    pipeline = Pipeline()
    responses = []

    for i, sent in enumerate(sentences):
        try:
            resp = await asyncio.wait_for(
                pipeline.process(sent, doc_id=f"hallmarks_of_pd-sent-{i:04d}", use_llm=False),
                timeout=60,
            )
            responses.append(resp)
        except Exception as e:
            logger.error("Pipeline error at sentence %d: %s", i, e)
            responses.append(None)

    total_matched = 0
    total_missed = 0
    all_matched = []
    all_missed = []

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

            matched, missed = _find_matches(entries, sent_responses)
            total_matched += len(matched)
            total_missed += len(missed)
            for item in matched:
                all_matched.append((sent_text[:60], item))
            for item in missed:
                all_missed.append((sent_text[:60], item))

    total = total_matched + total_missed
    coverage = total_matched / total * 100 if total > 0 else 0

    print(f"\n{'='*60}")
    print(f"GROUND TRUTH COVERAGE: {total_matched}/{total} ({coverage:.1f}%)")
    print(f"{'='*60}")

    if all_matched:
        print(f"\nMATCHED TRIPLETS ({len(all_matched)}):")
        for sent_preview, (uuid_val, subj, pred, obj) in all_matched:
            print(f"  [{uuid_val[:12]}...] {subj} -> {pred} -> {obj}")

    if all_missed:
        print(f"\nMISSED TRIPLETS ({len(all_missed)}):")
        for sent_preview, (uuid_val, subj, pred, obj) in all_missed:
            print(f"  [{uuid_val[:12]}...] {subj} -> {pred} -> {obj}")
            print(f"    Sentence: {sent_preview}...")

    assert coverage >= 1, f"Coverage too low: {coverage:.1f}%"

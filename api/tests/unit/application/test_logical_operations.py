"""Тесты логических операций генерации знаний (application/generation)."""

import pytest

from application.generation import LOGICAL, run_generation
from application.generation.provenance import build_knowledge_result


def _st(subj, pred, obj):
    return {"subject_text": subj, "predicate": pred, "object_text": obj}


CORPUS = [
    _st("A", "causes", "B"),
    _st("B", "leads to", "C"),
    _st("vitamin D", "activates", "immune system"),
    _st("immune system", "regulates", "inflammation"),
    _st("mitochondrial dysfunction", "be", "pillars of aging"),
]


class TestTransitivity:
    def test_chain_yields_a_to_c(self):
        res = run_generation(method=LOGICAL, statements=CORPUS, operation="transitivity", limit=10)
        new = [n for r in res for n in r["new_statements"]]
        assert ("A", "leads to", "C") in {(n["subject_text"], n["predicate"], n["object_text"]) for n in new}

    def test_includes_sources(self):
        res = run_generation(method=LOGICAL, statements=CORPUS, operation="transitivity", limit=10)
        assert all(r["source_statements"] for r in res)
        assert all(r["knowledge_method"] == LOGICAL for r in res)

    def test_empty_without_chain(self):
        res = run_generation(method=LOGICAL, statements=[_st("X", "causes", "Y")], operation="transitivity", limit=10)
        assert res == []


class TestPredicateInference:
    def test_reverse(self):
        res = run_generation(method=LOGICAL, statements=CORPUS, operation="predicate_inference", limit=10)
        new = [n for r in res for n in r["new_statements"]]
        assert ("immune system", "is activated by", "vitamin D") in {
            (n["subject_text"], n["predicate"], n["object_text"]) for n in new
        }

    def test_unknown_predicate_no_inference(self):
        res = run_generation(method=LOGICAL, statements=[_st("A", "is_a", "B")], operation="predicate_inference", limit=10)
        assert res == []


class TestContraposition:
    def test_causes(self):
        res = run_generation(method=LOGICAL, statements=CORPUS, operation="contraposition", limit=10)
        new = [n for r in res for n in r["new_statements"]]
        assert ("B", "does not cause", "A") in {(n["subject_text"], n["predicate"], n["object_text"]) for n in new}


class TestAllOperations:
    def test_envelope_shape(self):
        res = run_generation(method=LOGICAL, statements=CORPUS, limit=100)
        for r in res:
            assert r["knowledge_method"] == LOGICAL
            assert r["operation"]
            assert r["operation_label"]
            assert r["source_statements"]
            assert r["new_statements"]
            assert r["provenance"]["method"] == LOGICAL
            assert r["provenance"]["new_count"] == len(r["new_statements"])


def test_build_knowledge_result_dedup():
    r = build_knowledge_result(
        method=LOGICAL,
        operation="x",
        operation_label="X",
        source_statements=[_st("A", "causes", "B"), _st("A", "causes", "B")],
        new_statements=[_st("X", "r", "Y"), _st("X", "r", "Y")],
        description="d",
    )
    assert len(r["source_statements"]) == 1
    assert len(r["new_statements"]) == 1

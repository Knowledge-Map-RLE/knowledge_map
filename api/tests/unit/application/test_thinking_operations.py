"""Тесты операций мышления (application/generation/thinking_operations.py)."""

from application.generation import THINKING, run_generation
from application.generation.thinking_operations import thinking_operations


def _st(subj, pred, obj):
    return {"subject_text": subj, "predicate": pred, "object_text": obj}


CORPUS = [
    _st("vitamin D", "increases", "immune system"),
    _st("vitamin D", "decreases", "inflammation"),
    _st("aging", "causes", "frailty"),
    _st("frailty", "leads to", "decline in T cell function"),
    _st("mitochondrial dysfunction", "be", "pillars of aging"),
    _st("telomere shortening", "be", "pillars of aging"),
]


class TestOperations:
    def test_operations_catalog(self):
        ops = thinking_operations()
        assert "analysis" in ops
        assert "synthesis" in ops
        assert "comparison" in ops
        assert "abstraction" in ops
        assert "generalization" in ops
        assert "concretization" in ops
        assert "induction" in ops
        assert "deduction" in ops
        assert "analogy" in ops
        assert "causality" in ops
        assert "counterfactual" in ops
        assert "classification" in ops

    def test_analysis(self):
        res = run_generation(method=THINKING, statements=CORPUS, operation="analysis", limit=10)
        new = [n for r in res for n in r["new_statements"]]
        assert ("vitamin D", "relates to", "immune system") in {
            (n["subject_text"], n["predicate"], n["object_text"]) for n in new
        }

    def test_synthesis_grouped_by_subject(self):
        res = run_generation(method=THINKING, statements=CORPUS, operation="synthesis", limit=10)
        new = [n for r in res for n in r["new_statements"]]
        subjects = {n["subject_text"] for n in new}
        assert "vitamin D" in subjects

    def test_causality_chain(self):
        res = run_generation(method=THINKING, statements=CORPUS, operation="causality", limit=10)
        new = [n for r in res for n in r["new_statements"]]
        assert ("aging", "causes", "decline in T cell function") in {
            (n["subject_text"], n["predicate"], n["object_text"]) for n in new
        }

    def test_comparison(self):
        res = run_generation(method=THINKING, statements=CORPUS, operation="comparison", limit=10)
        new = [n for r in res for n in r["new_statements"]]
        # субъекты с общим предикатом 'be' сравнимы
        assert any(n["predicate"].startswith("is comparable") for n in new)

    def test_analogy(self):
        corp = [
            _st("stress", "increases", "inflammation"),
            _st("sedentary lifestyle", "increases", "inflammation"),
            _st("stress", "decreases", "sleep quality"),
        ]
        res = run_generation(method=THINKING, statements=corp, operation="analogy", limit=10)
        new = [n for r in res for n in r["new_statements"]]
        assert any(n["predicate"] == "likely also increases" and n["object_text"] == "inflammation" for n in new)

    def test_all_envelope(self):
        res = run_generation(method=THINKING, statements=CORPUS, limit=100)
        for r in res:
            assert r["knowledge_method"] == THINKING
            assert r["operation"]
            assert r["new_statements"]

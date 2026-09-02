"""Тесты силлогизмов (application/generation/syllogisms.py)."""

from application.generation import SYLLOGISM, run_generation
from application.generation.syllogisms import syllogism_moduses, syllogism_operations


def _st(subj, pred, obj):
    return {"subject_text": subj, "predicate": pred, "object_text": obj}


CAT_CHAIN = [
    _st("mitochondrial dysfunction", "be", "pillars of aging"),
    _st("pillars of aging", "be", "hallmarks of aging"),
]


class TestModusCatalog:
    def test_twenty_four_moduses(self):
        moduses = syllogism_moduses()
        assert len(moduses) == 24
        moods = {(m["mood"], m["figure"]) for m in moduses}
        assert len(moods) == 24
        # ключевые модусы присутствуют
        assert ("AAA-1", 1) in moods
        assert ("EAE-1", 1) in moods
        assert ("AOO-2", 2) in moods
        assert ("OAO-3", 3) in moods
        assert ("AAI-4", 4) in moods

    def test_operations_listed(self):
        assert "barbara_aaa" in syllogism_operations()
        assert "celarent_eae" in syllogism_operations()


class TestBarbara:
    def test_transitivity(self):
        res = run_generation(method=SYLLOGISM, statements=CAT_CHAIN,
                             operation="barbara_aaa", limit=10)
        new = [n for r in res for n in r["new_statements"]]
        assert ("mitochondrial dysfunction", "is_a", "hallmarks of aging") in {
            (n["subject_text"], n["predicate"], n["object_text"]) for n in new
        }

    def test_no_self_loop(self):
        res = run_generation(method=SYLLOGISM, statements=CAT_CHAIN,
                             operation="barbara_aaa", limit=10)
        for r in res:
            for n in r["new_statements"]:
                assert n["subject_text"].lower() != n["object_text"].lower()

    def test_no_duplicate_if_existing(self):
        statements = CAT_CHAIN + [_st("mitochondrial dysfunction", "is_a", "hallmarks of aging")]
        res = run_generation(method=SYLLOGISM, statements=statements,
                             operation="barbara_aaa", limit=10)
        new = [n for r in res for n in r["new_statements"]]
        assert ("mitochondrial dysfunction", "is_a", "hallmarks of aging") not in {
            (n["subject_text"], n["predicate"], n["object_text"]) for n in new
        }


class TestCelarent:
    def test_negative_conclusion(self):
        statements = [
            _st("vitamin D", "be", "essential nutrient"),
            _st("cytokine", "is not", "essential nutrient"),
        ]
        res = run_generation(method=SYLLOGISM, statements=statements,
                             operation="celarent_eae", limit=10)
        new = [n for r in res for n in r["new_statements"]]
        assert ("cytokine", "is not", "vitamin D") in {
            (n["subject_text"], n["predicate"], n["object_text"]) for n in new
        }

    def test_negative_without_positive_no_result(self):
        res = run_generation(method=SYLLOGISM, statements=[_st("A", "is not", "B")],
                             operation="celarent_eae", limit=10)
        assert res == []

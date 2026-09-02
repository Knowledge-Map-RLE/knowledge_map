"""Тесты repository: сверка существующего знания (check_statements)."""

from unittest.mock import patch

from adapters.repositories.pattern_miner_repository import PatternMinerRepository


EXISTING_ROWS = [
    # (subj, pred, obj, doc)
    ("aging", "be", "a natural process", "D1"),
    ("vitamin d", "decreases", "immune system", "D2"),
]


def _check(triplets, rows=EXISTING_ROWS):
    repo = PatternMinerRepository()
    with patch.object(repo, "_load_exists_index", return_value=rows, autospec=True):
        return repo.check_statements(triplets)


class TestCheckStatements:
    def test_new(self):
        report = _check([
            {"subject_text": "vitamin D", "predicate": "activates", "object_text": "macrophages"}
        ])
        assert report[0]["status"] == "new"
        assert report[0]["check_mode"] == "new"

    def test_exists(self):
        report = _check([
            {"subject_text": "Aging", "predicate": "be", "object_text": "a natural process"}
        ])
        assert report[0]["status"] == "exists"
        assert report[0]["evidence_doc_ids"] == ["D1"]

    def test_conflicts_direction(self):
        report = _check([
            {"subject_text": "vitamin D", "predicate": "increases", "object_text": "immune system"}
        ])
        assert report[0]["status"] == "conflicts"
        assert report[0]["conflicting_direction"] == "down"

    def test_new_when_no_dir_conflict(self):
        rows = [("aging", "is_a", "process", "D1")]
        report = _check([
            {"subject_text": "aging", "predicate": "is_a", "object_text": "disease"}
        ], rows)
        assert report[0]["status"] == "new"

    def test_empty_input(self):
        assert _check([]) == []

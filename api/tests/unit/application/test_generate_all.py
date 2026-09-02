"""Тесты автономной генерации знания (PatternMinerService.generate_all)."""

from unittest.mock import MagicMock, patch

import pytest

from services.pattern_miner_service import PatternMinerService


def _mk_repo():
    repo = MagicMock()
    repo.load_corpus.return_value = [
        {"doc_id": "D1", "statements": [
            {"subject_text": "vitamin D", "predicate": "be", "object_text": "essential nutrient",
             "subject_type": "concept", "object_type": "concept"},
            {"subject_text": "essential nutrient", "predicate": "be", "object_text": "pillars of aging",
             "subject_type": "concept", "object_type": "concept"},
            {"subject_text": "vitamin D", "predicate": "increases", "object_text": "immune system",
             "subject_type": "concept", "object_type": "concept"},
            {"subject_text": "aging", "predicate": "causes", "object_text": "immunosenescence",
             "subject_type": "concept", "object_type": "concept"},
            {"subject_text": "immunosenescence", "predicate": "leads to", "object_text": "frailty",
             "subject_type": "concept", "object_type": "concept"},
        ], "count": 5},
    ]
    repo.check_statements.return_value = [
        {"subject_text": "x", "predicate": "y", "object_text": "z", "status": "new", "evidence_doc_ids": []}
    ]
    return repo


@pytest.mark.asyncio
async def test_generate_all_produces_all_four_methods():
    svc = PatternMinerService(repo=_mk_repo())
    fake_pattern = {
        "id": "p1", "size": 2, "edges_count": 1, "support": 2,
        "nodes": ["concept", "concept"], "edges": [[0, 1, "increases"]],
    }
    with (
        patch("services.pattern_miner_service.mine_assertion_patterns",
              return_value=[fake_pattern]),
        patch("services.pattern_miner_service.apply_pattern",
              return_value={"gaps": [
                  {"subject_text": "vitamin D", "predicate": "increases", "object_text": "macrophages"},
              ]}),
        patch.object(svc, "repo", _mk_repo()),
    ):
        res = await svc.generate_all(
            check_existing=True,
            limit_per_method=20,
            min_support=0.5,
            corpus_doc_ids=["D1"],
        )
    assert res["success"] is True
    methods = {m["method"] for m in res["methods"]}
    assert {"pattern", "logical", "syllogism", "thinking"} == methods
    for m in res["methods"]:
        assert m["count"] >= 0
        for g in m["groups"]:
            assert g["knowledge_method"] == m["method"]
            assert g["new_statements"]


@pytest.mark.asyncio
async def test_generate_all_attaches_checks():
    svc = PatternMinerService(repo=_mk_repo())
    with (
        patch("services.pattern_miner_service.mine_assertion_patterns", return_value=[]),
        patch.object(svc, "repo", _mk_repo()),
    ):
        res = await svc.generate_all(check_existing=True)
    for m in res["methods"]:
        for g in m["groups"]:
            for st in g["new_statements"]:
                assert "check" in st


@pytest.mark.asyncio
async def test_generate_all_when_no_statements():
    repo = MagicMock()
    repo.load_corpus.return_value = []
    svc = PatternMinerService(repo=repo)
    res = await svc.generate_all()
    assert res["success"] is True
    assert res["methods"] == []
    assert res["corpus_pool_size"] == 0
"""Явный корпус, права доступа, неизменяемость и отсутствие AI-вызовов."""
import copy

import pytest

from application.compare_article_maps import CompareArticleMaps, validate_reference, control_metrics
from domain.article_maps import ArticleMapError, ArticleMapAccessDenied


def map_result(article, run):
    s = {"statement_id": "S1", "predicate": "measured using", "roles": [{"role": "subject", "concept_id": "C1", "knowledge_id": None}],
         "quantifier": "all", "modality": None, "temporal_context": "2010–2012", "conditions": [], "negated": False,
         "qualifiers": {"attributes": [{"name": "rate", "value": 22.5, "unit": "percent"}]}, "provenance": {"unit_ids": ["U1"]}}
    return {"article_id": article, "pipeline_id": "text_reified", "run_id": run, "source": {"sha256": article},
        "graph": {"schema_version": 6, "concepts": [{"id": "C1", "display_text": "MCI"}], "nodes": [], "transitions": [],
            "knowledge": [{"knowledge_id": "K1", "kind": "state", "knowledge_kind": "definition", "display_text": "MCI definition",
                "action_status": None, "semantic_frame": {"logic": "single", "statements": [s]}, "provenance": {"unit_ids": ["U1"]}}]}}


class Maps:
    def __init__(self): self.calls = []
    def get(self, article, pipeline, owner, run):
        self.calls.append((article, pipeline, owner, run))
        if article == "forbidden": raise ArticleMapAccessDenied("Denied")
        return map_result(article, run)


class Repository:
    def __init__(self): self.results = {}; self.writes = 0
    def get(self, cid, owner): return self.results.get(cid)
    def save(self, result, owner): self.results[result["comparison_id"]] = result; self.writes += 1


class Controls:
    def select(self, references): return {"version": "test", "references": references, "pairs": []}


def ref(article): return {"article_id": article, "pipeline_id": "text_reified", "run_id": "run-" + article}


def test_reads_only_explicit_runs_and_is_reproducible(monkeypatch):
    import httpx
    monkeypatch.setattr(httpx.Client, "send", lambda *a, **k: (_ for _ in ()).throw(AssertionError("HTTP prohibited")))
    maps, repository = Maps(), Repository()
    app = CompareArticleMaps(maps, repository, Controls())
    first = app.execute(ref("target"), [ref("source")], "owner")
    second = app.execute(ref("target"), [ref("source")], "owner")
    assert first == second and repository.writes == 1
    assert maps.calls == [(a, "text_reified", "owner", "run-"+a) for a in ("target", "source", "target", "source")]
    assert first["analysis"]["model_calls"] == 0


def test_all_owners_checked_before_computing_or_saving():
    repository = Repository()
    with pytest.raises(ArticleMapAccessDenied):
        CompareArticleMaps(Maps(), repository, Controls()).execute(ref("target"), [ref("forbidden")], "owner")
    assert repository.writes == 0


def test_duplicate_target_or_implicit_reference_rejected():
    with pytest.raises(ArticleMapError): validate_reference(ref("a") | {"latest": True})
    with pytest.raises(ArticleMapError): CompareArticleMaps(Maps(), Repository(), Controls()).execute(ref("a"), [ref("a")], "owner")


def test_control_retrieval_uses_actual_positions_and_exposes_differences():
    pairs = [{"left_knowledge_id": "K1", "right_article_id": "source", "right_knowledge_id": "K2", "text_rank": 2,
        "semantic_rank": 11, "hybrid_rank": 5, "relations": ["partial"], "pair_id": "pair", "statement_matches": [{"differences": [{"field": "units"}]}]}]
    control = {"pairs": [{"id": "6", "kind": "citation", "left_knowledge_ids": ["K1"], "right_article_id": "source",
        "right_knowledge_ids": ["K2"], "expected_relations": ["partial"]}]}
    result = control_metrics(pairs, control)
    assert result["retrieval_at_k"]["text"]["1"]["found"] == 0
    assert result["retrieval_at_k"]["hybrid"]["5"]["found"] == 1
    assert result["observations"][0]["detected_difference_fields"] == ["units"]

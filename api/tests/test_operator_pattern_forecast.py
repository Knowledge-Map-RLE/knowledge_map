"""Проверки переноса формы авторского перехода без переноса научного факта."""
from copy import deepcopy
from hashlib import sha256

import pytest

from domain.article_maps import ArticleMapError
from domain.operator_pattern_forecast import (
    evaluate,
    forecast_from_rows,
    patterns_for_map,
    run_lopo,
    validate_map_snapshot,
)


def article(article_id, *, transition=True):
    text = "Synthetic source fragment 🐁"
    source = {
        "text": text,
        "sha256": sha256(text.encode("utf-8")).hexdigest(),
        "offset_encoding": "unicode_codepoints",
        "content_end": len(text),
        "units": [{"id": "U1", "start": 0, "end": len(text), "text": text}],
    }
    concepts = [
        {"id": "C1", "display_text": "Review action", "aliases": []},
        {"id": "C2", "display_text": "Study population", "aliases": []},
        {"id": "C3", "display_text": "MCI incidence", "aliases": []},
    ]

    def knowledge(knowledge_id, predicate, kind, knowledge_kind, action_status, roles, display_text):
        return {
            "knowledge_id": knowledge_id,
            "kind": kind,
            "knowledge_kind": knowledge_kind,
            "action_status": action_status,
            "display_text": display_text,
            "semantic_frame": {
                "logic": "single",
                "statements": [{
                    "statement_id": knowledge_id + "S1",
                    "predicate": predicate,
                    "roles": roles,
                    "quantifier": None,
                    "modality": None,
                    "temporal_context": None,
                    "conditions": ["synthetic study setting"],
                    "negated": False,
                    "qualifiers": {"attributes": []},
                    "provenance": {"unit_ids": ["U1"]},
                }],
            },
            "provenance": {"unit_ids": ["U1"]},
        }

    role_c1 = {"role": "subject", "concept_id": "C1", "knowledge_id": None}
    role_c2 = {"role": "subject", "concept_id": "C2", "knowledge_id": None}
    role_c3 = {"role": "subject", "concept_id": "C3", "knowledge_id": None}
    knowledge_items = [
        knowledge("K1", "search literature", "action", "operation", "performed", [role_c1], "Review action A"),
        knowledge("K2", "extract study data", "action", "operation", "performed", [role_c2], "Review action B"),
        knowledge("K3", "mci incidence", "state", "result", None, [role_c3], "Reported frequency"),
    ]
    transitions = [{"sources": ["N2"], "target": "N3", "unit_ids": ["U1"]}] if transition else []
    edges = [{"source": source_id, "target": group["target"]}
             for group in transitions for source_id in group["sources"]]
    return {
        "article_id": article_id,
        "pipeline_id": "text_reified",
        "run_id": "run-" + article_id,
        "article_title": "Synthetic article",
        "graph_schema_version": 6,
        "source": source,
        "graph": {
            "schema_version": 6,
            "concepts": concepts,
            "knowledge": knowledge_items,
            "nodes": [
                {"id": "N1", "knowledge_id": "K1", "rank": 0},
                {"id": "N2", "knowledge_id": "K2", "rank": 1},
                {"id": "N3", "knowledge_id": "K3", "rank": 2},
            ],
            "transitions": transitions,
            "edges": edges,
        },
    }


def row(pattern_id="p1", *, premise="review", conclusion="frequency"):
    pattern = {
        "id": pattern_id,
        "arity": 1,
        "premises": [{"kind": "action", "statements": []}],
        "conclusion": {"kind": "state", "statements": []},
    }
    return {"pattern": pattern, "premise_text": premise, "conclusion_text": conclusion,
            "premise_id": "K1", "conclusion_id": "K2"}


def test_operator_pattern_drops_article_specific_participants_but_keeps_roles():
    first, second = article("first"), article("second")
    first["graph"]["knowledge"][1]["semantic_frame"]["statements"][0]["roles"][0]["concept_id"] = "C2"
    second["graph"]["knowledge"][1]["semantic_frame"]["statements"][0]["roles"][0]["concept_id"] = "C3"
    left = patterns_for_map(first, "graph")[0][0]["pattern"]
    right = patterns_for_map(second, "graph")[0][0]["pattern"]
    assert left["id"] == right["id"]
    assert left["premises"][0]["statements"][0]["operator_family"] == "review_procedure"
    assert left["conclusion"]["statements"][0]["operator_family"] == "reported_frequency"


def test_minimum_publication_support_and_target_leakage_are_enforced():
    same_pattern = row()
    one_source = forecast_from_rows({"source-a": [same_pattern]}, mode="graph", min_support=2)
    two_sources = forecast_from_rows({"source-a": [same_pattern], "source-b": [same_pattern]},
                                     mode="graph", min_support=2)
    assert not one_source["predictions"]
    assert two_sources["predictions"][0]["support"] == 2
    target = article("target")
    leaked = forecast_from_rows({"target": [same_pattern]}, mode="graph")
    with pytest.raises(ArticleMapError, match="leaked"):
        evaluate(leaked, target)
    held_out = forecast_from_rows({"source-a": [same_pattern]}, mode="graph")
    score = evaluate(held_out, target)
    assert score["target_excluded_from_training"] is True
    assert score["target_read_order_verified"] is False


def test_lopo_does_not_train_on_target_and_records_permutation_diagnostics():
    maps = [article("one"), article("two"), article("three")]
    before = deepcopy(maps)
    result = run_lopo(maps, candidate_limit=20, min_support=1, permuted_seeds=[0, 1])
    assert maps == before
    assert result["corpus_size"] == 3 and result["model_calls"] == 0
    assert result["network_disabled"] is True and result["confirmatory"] is False
    assert result["sealed_blind_evaluation"] is False
    for mode, folds in result["patterns_per_source"].items():
        assert set(folds) == {"one", "two", "three"}
        for target_id, prediction in folds.items():
            assert target_id not in prediction["training_source_ids"]
            assert len(prediction["training_source_ids"]) == 2
    assert set(result["permuted_diagnostics"]) == {0, 1}
    for per_article in result["permuted_diagnostics"].values():
        assert set(per_article) == {"one", "two", "three"}
        assert all(item["original_groups"] == item["permuted_groups"]
                   and item["skipped_groups"] == 0 for item in per_article.values())


@pytest.mark.parametrize("mutation, message", [
    ("cycle", "DAG"),
    ("unknown_source", "Invalid author dependency group"),
    ("outside_content", "Bibliography cannot support"),
])
def test_invalid_dag_links_and_bibliographic_provenance_are_rejected(mutation, message):
    value = article("sample")
    if mutation == "cycle":
        value["graph"]["edges"].append({"source": "N3", "target": "N2"})
    elif mutation == "unknown_source":
        value["graph"]["transitions"][0]["sources"] = ["UNKNOWN"]
    else:
        value["source"]["content_end"] = len(value["source"]["text"]) - 1
    with pytest.raises(ArticleMapError, match=message):
        validate_map_snapshot(value)

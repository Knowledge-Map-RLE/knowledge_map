from collections import Counter
from pathlib import Path

from tools import run_pmc10000452_free_shape_forecast as forecast_tool


def _article(article_id, *, cited=False):
    shape = {
        "arity": 1,
        "source_types": ["action/operation"],
        "target_type": "state/result",
    }
    return {
        "article_id": article_id,
        "source_sha256": f"sha-{article_id}",
        "raw_sha256": f"map-sha-{article_id}",
        "graph_sha256": f"graph-sha-{article_id}",
        "source_text": (
            "Reference DOI 10.3390/healthcare11050703"
            if cited else f"full text for {article_id}"
        ),
        "shapes": [shape],
        "usage_shapes": [{"usage": "result", **shape}],
        "node_type_counts": Counter({
            "action/operation": 1,
            "state/result": 1,
        }),
    }


def test_forecast_builder_excludes_direct_citers_without_receiving_target_graph(monkeypatch):
    training_articles = {
        "paper-a": _article("paper-a"),
        "paper-b": _article("paper-b"),
        "paper-cites-target": _article("paper-cites-target", cited=True),
    }
    monkeypatch.setattr(
        "tools.run_full19_transition_pattern_forecast._load_articles",
        lambda path: (training_articles, {"sha256": "manifest-hash", "source_count": 3}),
    )

    result = forecast_tool._build_forecast(Path("unused-manifest.json"))

    assert result["target_graph_read_before_seal"] is False
    assert result["training_article_ids"] == ["paper-a", "paper-b"]
    assert [row["citing_article_id"] for row in result["direct_citation_exclusions"]] == [
        "paper-cites-target"
    ]
    assert result["candidate_modes"]["dependency_graph"][0]["article_support"] == [
        "paper-a",
        "paper-b",
    ]


def test_forecast_builder_records_explicit_same_cohort_exclusion(monkeypatch):
    cohort_source = "pilot-pmc10000452-pmc8775386-953d8a7973426b47"
    training_articles = {
        "paper-a": _article("paper-a"),
        "paper-b": _article("paper-b"),
        cohort_source: _article(cohort_source),
    }
    monkeypatch.setattr(
        "tools.run_full19_transition_pattern_forecast._load_articles",
        lambda path: (training_articles, {"sha256": "manifest-hash", "source_count": 3}),
    )

    result = forecast_tool._build_forecast(
        Path("unused-manifest.json"),
        (cohort_source,),
    )

    assert cohort_source in result["explicit_exclusion_ids"]
    assert result["training_article_count"] == 2
    assert result["explicit_source_exclusions"] == [{
        "citing_article_id": cohort_source,
        "source_sha256": f"sha-{cohort_source}",
        "reason": "карта отнесена к той же исследовательской когорте",
    }]
    assert result["direct_citation_exclusions"] == []


def test_target_evaluator_scores_shapes_after_forecast():
    shape = {
        "arity": 1,
        "source_types": ["action/operation"],
        "target_type": "state/result",
    }
    forecast = {
        "forecast_sha256": "sealed-hash",
        "candidate_modes": {
            "dependency_graph": [{
                "signature_id": forecast_tool._shape_id(shape),
                "shape": shape,
                "article_support": ["paper-a", "paper-b"],
            }],
            "without_edges": [],
            "dependency_graph_with_usage": [],
        },
    }
    target = {
        "article_id": forecast_tool.TARGET_ARTICLE_ID,
        "graph_schema_version": 6,
        "run_id": "target-run",
        "graph": {
            "nodes": [
                {"id": "n1", "knowledge_id": "k1"},
                {"id": "n2", "knowledge_id": "k2"},
            ],
            "knowledge": [
                {"knowledge_id": "k1", "kind": "action", "knowledge_kind": "operation"},
                {"knowledge_id": "k2", "kind": "state", "knowledge_kind": "result"},
            ],
            "transitions": [{
                "sources": ["n1"],
                "target": "n2",
                "usage": "result",
            }],
        },
    }

    result = forecast_tool._evaluate(
        forecast,
        target,
        {"graph_sha256": "target-graph-hash"},
    )

    assert result["technical_validation"]["forecast_sealed_before_target_graph_read"] is True
    assert result["mode_summary"]["dependency_graph"]["matched_shape_count"] == 1
    assert result["mode_summary"]["without_edges"]["matched_shape_count"] == 0
    assert result["scientific_content_predicted"] is False

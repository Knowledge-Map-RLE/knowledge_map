from collections import Counter

from tools.run_full19_transition_pattern_forecast import (
    _citation_matches,
    _cooccurrence_predictions,
    _graph_predictions,
    _paired_comparison,
    _score,
    _structure_from_usage_signature,
    _top_k_score,
)
from domain.article_maps import fingerprint


def test_graph_pattern_requires_support_from_distinct_articles():
    shape = {"arity": 1, "source_types": ["action/operation"], "target_type": "state/result"}
    training = {
        "a": {"shapes": [shape, shape]},
        "b": {"shapes": [shape]},
    }

    candidates, support = _graph_predictions(training)

    assert candidates == {next(iter(support))}
    assert support[next(iter(candidates))] == {"a", "b"}


def test_cooccurrence_control_uses_node_types_without_reading_edges():
    left = {
        "node_type_counts": Counter({"state/observation": 2, "state/conclusion": 1}),
        "shapes": [],
    }
    right = {
        "node_type_counts": Counter({"state/observation": 2, "state/conclusion": 1}),
        "shapes": [{"arity": 1, "source_types": ["action/operation"], "target_type": "state/result"}],
    }

    left_candidates, _ = _cooccurrence_predictions({"a": left, "b": left})
    right_candidates, _ = _cooccurrence_predictions({"a": right, "b": right})

    assert left_candidates == right_candidates


def test_cooccurrence_requires_enough_occurrences_for_distinct_source_and_target():
    training = {
        "a": {"node_type_counts": Counter({"state/observation": 1})},
        "b": {"node_type_counts": Counter({"state/observation": 1})},
    }

    candidates, _ = _cooccurrence_predictions(training)

    assert candidates == set()


def test_citation_audit_detects_doi_pmcid_and_full_title():
    target = {
        "citation_keys": {
            "doi": "10.5555/example.2020",
            "own_pmcid": "pmc12345",
            "title": "A Complete Example Study of Older Adults",
            "title_key": "a complete example study of older adults",
        }
    }
    source = {
        "source_text": (
            "References: doi 10.5555/example.2020. "
            "PMC12345. A Complete Example Study of Older Adults."
        )
    }

    matches = _citation_matches(target, source)

    assert {item["kind"] for item in matches} == {"doi", "pmcid", "exact_title"}
    assert all(item["start"] < item["end"] for item in matches)
    assert all(item["offset_encoding"] == "normalized_source_text_codepoints" for item in matches)
    assert all(item["snippet"] for item in matches)


def test_score_reports_unique_shapes_and_transition_coverage():
    shape = {"arity": 1, "source_types": ["state/observation"], "target_type": "state/conclusion"}

    result = _score({fingerprint(shape)}, [shape, shape])

    assert result["matched_shape_count"] == 1
    assert result["target_transition_count"] == 2
    assert result["covered_target_transition_count"] == 2
    assert result["target_transition_coverage"] == 1.0


def test_equal_candidate_budget_ranks_by_training_support_only():
    first = {"arity": 1, "source_types": ["action/operation"], "target_type": "state/result"}
    second = {"arity": 1, "source_types": ["state/observation"], "target_type": "state/conclusion"}
    support = {fingerprint(first): {"a", "b", "c"}, fingerprint(second): {"a", "b"}}
    catalog = {fingerprint(first): first, fingerprint(second): second}

    result = _top_k_score(support, catalog, [first], 1)

    assert result["matched_shape_count"] == 1
    assert result["predicted_shape_count"] == 1
    assert result["selected_support"][0]["shape"] == first


def test_paired_comparison_counts_article_level_wins_losses_and_ties():
    folds = [
        {
            "top_k_scores": {
                "20": {
                    "edge_patterns": {"matched_shape_count": 3},
                    "cooccurrence": {"matched_shape_count": 1},
                }
            }
        },
        {
            "top_k_scores": {
                "20": {
                    "edge_patterns": {"matched_shape_count": 0},
                    "cooccurrence": {"matched_shape_count": 2},
                }
            }
        },
        {
            "top_k_scores": {
                "20": {
                    "edge_patterns": {"matched_shape_count": 1},
                    "cooccurrence": {"matched_shape_count": 1},
                }
            }
        },
    ]

    result = _paired_comparison(folds, "20")

    assert result["graph_wins"] == 1
    assert result["no_edge_wins"] == 1
    assert result["ties"] == 1
    assert result["graph_matched_shapes"] == 4
    assert result["no_edge_matched_shapes"] == 4


def test_usage_signature_projects_to_same_structural_form_without_losing_usage():
    signature = {
        "usage": "result",
        "arity": 1,
        "source_types": ["action/operation"],
        "target_type": "state/result",
    }

    assert _structure_from_usage_signature(signature) == {
        "arity": 1,
        "source_types": ["action/operation"],
        "target_type": "state/result",
    }
    assert signature["usage"] == "result"

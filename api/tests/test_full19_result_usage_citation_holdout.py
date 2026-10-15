from tools.run_full19_result_usage_citation_holdout import (
    _citation_matches,
    _predictions,
)


def test_citation_match_finds_author_year_table_reference():
    matches = _citation_matches(
        "systematic-review",
        "Results are summarized in Table 2. Caracciolo 2008 [33] reported incidence.",
    )

    assert [(row["target_article_id"], row["matched_pattern"]) for row in matches] == [
        (
            "caracciolo2008",
            r"Caracciolo\s+(?:B\.?\s*)?2008(?:\s*\[[^\]]+\])?",
        )
    ]


def test_citation_match_finds_title_reference_across_line_breaks():
    matches = _citation_matches(
        "systematic-review",
        "Reference: Age-specific and Sex-specific Prevalence and Incidence of\n"
        "Mild Cognitive Impairment, published in 2012.",
    )

    assert len(matches) == 1
    assert matches[0]["target_article_id"] == "katz2012"


def test_citation_match_normalizes_ocr_hyphenation_in_reference_title():
    matches = _citation_matches(
        "older-pdf-map",
        "Caracciolo B, Palmer K, Monastero R, et al. Occurrence of cognitive impair-\n"
        "ment and dementia in the community. Neurology 2008;70:1778-1785.",
    )

    assert len(matches) == 1
    assert matches[0]["target_article_id"] == "caracciolo2008"


def test_citation_match_detects_two_column_pdf_reference_with_spread_author_and_year():
    matches = _citation_matches(
        "two-column-pdf-map",
        "Caracciolo B, Palmer K, Monastero R et al. Occurrence of cognitive impair- "
        "activities of daily living in other MCI subtypes.\nment and dementia in the "
        "community: A 9-year-long prospective study. Neu- rology 2008;70:1778–1785.",
    )

    assert len(matches) == 1
    assert matches[0]["target_article_id"] == "caracciolo2008"


def test_citation_match_does_not_treat_target_self_as_training_leakage():
    matches = _citation_matches(
        "roberts2012",
        "The incidence of MCI differs by subtype and is higher in men.",
    )

    assert matches == []


def test_free_category_forecast_does_not_read_target_operations():
    def map_row(article_id: str, operations: list[str], edges: list[list[str]]) -> dict:
        outputs = ["reported_frequency"]
        return {
            "article_id": article_id,
            "operator_families": operations,
            "output_families": outputs,
            "graph_links": edges,
            "cooccurrence_links": [
                [operation, outcome] for operation in operations for outcome in outputs
            ],
            "graph_evidence": {},
        }

    rows = {
        "train-1": {
            "all_map": map_row("train-1", ["incidence_estimation"],
                                [["incidence_estimation", "reported_frequency"]]),
            "result_map": map_row("train-1", ["incidence_estimation"],
                                   [["incidence_estimation", "reported_frequency"]]),
        },
        "train-2": {
            "all_map": map_row("train-2", ["incidence_estimation"],
                                [["incidence_estimation", "reported_frequency"]]),
            "result_map": map_row("train-2", ["incidence_estimation"],
                                   [["incidence_estimation", "reported_frequency"]]),
        },
        "target": {
            "all_map": map_row("target", ["incidence_estimation"], []),
            "result_map": map_row("target", ["incidence_estimation"], []),
        },
    }
    truth = {"target": {("incidence_estimation", "reported_frequency")}}

    known_operation_fold = _predictions(rows, "target", set(), truth)
    rows["target"]["all_map"]["operator_families"] = ["unseen_operation"]
    unknown_operation_fold = _predictions(rows, "target", set(), truth)

    assert known_operation_fold["modes"]["free_dependency_edges_all_usage"]["matched_pairs"] == [
        ["incidence_estimation", "reported_frequency"]
    ]
    assert unknown_operation_fold["modes"]["free_dependency_edges_all_usage"]["matched_pairs"] == [
        ["incidence_estimation", "reported_frequency"]
    ]
    assert known_operation_fold["modes"]["dependency_edges_all_usage"]["matched_pairs"] != (
        unknown_operation_fold["modes"]["dependency_edges_all_usage"]["matched_pairs"]
    )

from __future__ import annotations

import random

from domain.action_result_free_transfer import (
    _permute_training_outcomes, forecast_free, score_forecasts,
    score_permutations, seal_forecasts,
)
from tools.run_action_result_free_citation_audit import (
    find_direct_citation, normalize_citation_text,
)


def _record(article_id: str, pair: list[str], *, family: str | None = None,
            cooccurrence: list[list[str]] | None = None) -> dict:
    return {
        "article_id": article_id,
        "support_family": family or f"publication:{article_id}",
        "graph_links": [pair],
        "cooccurrence_links": cooccurrence if cooccurrence is not None else [pair],
        "direct_links": [{"operation_family": pair[0], "outcome_family": pair[1]}],
    }


def test_free_forecast_uses_only_training_inventory_and_family_support() -> None:
    training = [
        _record("A", ["cohort_analysis", "reported_frequency"], family="pub-A"),
        _record("B", ["cohort_analysis", "reported_frequency"], family="pub-B"),
        _record("C", ["measure", "reported_association"], family="pub-C"),
        _record("D", ["measure", "reported_association"], family="pub-C"),
    ]

    forecast = forecast_free(training, minimum_support=2)

    assert forecast["predictions"]["graph"] == [["cohort_analysis", "reported_frequency"]]
    assert forecast["predictions"]["without_dependencies"] == forecast["predictions"]["graph"]
    assert forecast["ranked_candidates"]["graph"][0]["distinct_source_families"] == 2


def test_citation_exclusion_removes_citer_before_forecast() -> None:
    records = [
        _record("A", ["analysis", "frequency"]),
        _record("B", ["analysis", "frequency"]),
        _record("C", ["analysis", "frequency"]),
        _record("T", ["other", "parameter"]),
    ]
    exclusions = {article_id: [] for article_id in (row["article_id"] for row in records)}
    exclusions["T"] = [{"target_article_id": "T", "citing_article_id": "C"}]

    sealed = seal_forecasts(records, exclusions, minimum_support=2)
    target_fold = next(row for row in sealed["folds"] if row["target_article_id"] == "T")
    scored = score_forecasts(records, sealed)
    target_score = next(row for row in scored["folds"] if row["target_article_id"] == "T")

    assert target_fold["training_article_ids"] == ["A", "B"]
    assert target_fold["predictions"]["graph"] == [["analysis", "frequency"]]
    assert target_score["scores"]["graph"]["matched"] == []
    assert sealed["target_operation_families_used"] is False
    assert sealed["target_outcomes_or_dependencies_used"] is False


def test_permutation_summary_reports_null_distribution_and_control_diversity() -> None:
    records = []
    for article_id in ("A", "B", "C", "T"):
        records.append({
            "article_id": article_id,
            "support_family": f"publication:{article_id}",
            "graph_links": [["analysis", "frequency"], ["experiment", "effect"]],
            "cooccurrence_links": [["analysis", "frequency"], ["experiment", "effect"]],
            "direct_links": [
                {"operation_family": "analysis", "outcome_family": "frequency"},
                {"operation_family": "experiment", "outcome_family": "effect"},
            ],
        })
    exclusions = {row["article_id"]: [] for row in records}
    sealed = seal_forecasts(records, exclusions, minimum_support=2)
    observed = score_forecasts(records, sealed)

    controls = score_permutations(records, exclusions, records, [1, 2, 3], observed,
                                  minimum_support=2)

    assert controls["seed_count"] == 3
    assert controls["summary"]["graph"]["mean_hits"] >= 0
    assert controls["summary"]["graph"]["top_k"]["3"]["runs_at_least_observed"] >= 0
    assert controls["unique_prediction_sets"] >= 1
    assert controls["unique_ranked_profiles"] >= 1
    assert controls["changed_sources_min"] >= 0


def test_global_training_permutation_preserves_operation_and_outcome_marginals() -> None:
    training = [
        {
            "article_id": "A", "support_family": "pub-A",
            "graph_links": [["analysis", "frequency"], ["experiment", "effect"]],
            "cooccurrence_links": [["analysis", "frequency"]],
            "direct_links": [
                {"operation_family": "analysis", "outcome_family": "frequency"},
                {"operation_family": "experiment", "outcome_family": "effect"},
            ],
        },
        {
            "article_id": "B", "support_family": "pub-B",
            "graph_links": [["analysis", "association"], ["experiment", "frequency"]],
            "cooccurrence_links": [["analysis", "association"]],
            "direct_links": [
                {"operation_family": "analysis", "outcome_family": "association"},
                {"operation_family": "experiment", "outcome_family": "frequency"},
            ],
        },
    ]

    permuted = _permute_training_outcomes(training, random.Random(17))

    from collections import Counter
    original_outcomes = Counter(edge["outcome_family"]
                                for row in training for edge in row["direct_links"])
    permuted_outcomes = Counter(pair[1] for row in permuted for pair in row["graph_links"])
    for original, randomized in zip(training, permuted):
        original_operations = Counter(edge["operation_family"]
                                      for edge in original["direct_links"])
        randomized_operations = Counter(pair[0] for pair in randomized["graph_links"])
        assert randomized_operations == original_operations
        assert randomized["cooccurrence_links"] == original["cooccurrence_links"]
    assert permuted_outcomes == original_outcomes


def test_citation_normalization_joins_pdf_line_wrap_hyphenation() -> None:
    assert normalize_citation_text("cognitive impair-\n ment in older adults") == \
        "cognitive impairment in older adults"


def test_direct_citation_match_uses_exact_doi_title_and_pmcid_and_ignores_self() -> None:
    target = {
        "article_id": "PMC12345",
        "title": "Example Cohort Study of Cognitive Aging",
        "normalized_title": normalize_citation_text("Example Cohort Study of Cognitive Aging"),
        "doi": "10.1000/example.1",
        "normalized_doi": normalize_citation_text("10.1000/example.1"),
        "pmcid": "PMC12345",
        "author_year": {"author": "caracciolo", "year": "2008"},
    }

    by_title = find_direct_citation("PMC99999", "References: Example Cohort Study of Cognitive Aging.", target)
    by_doi = find_direct_citation("PMC99999", "https://doi.org/10.1000/example.1", target)
    by_pmcid = find_direct_citation("PMC99999", "See PMC12345 for details", target)
    by_author_year = find_direct_citation(
        "PMC99999", "Caracciolo B, Palmer K. Occurrence of cognitive impairment. Neurology 2008;70.", target)
    self_match = find_direct_citation("PMC12345", "Example Cohort Study of Cognitive Aging", target)

    assert by_title and "title" in by_title["matched_identifiers"]
    assert by_doi and "doi" in by_doi["matched_identifiers"]
    assert by_pmcid and "pmcid" in by_pmcid["matched_identifiers"]
    assert by_author_year and "author_year" in by_author_year["matched_identifiers"]
    assert self_match is None


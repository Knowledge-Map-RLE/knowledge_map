from copy import deepcopy

from domain.action_result_transfer import (
    _permuted_records,
    _expected_hits_at_k,
    classify_operation,
    classify_outcome,
    extract_article,
    score_predictions,
    seal_permuted_predictions,
    seal_predictions,
)


def _snapshot(article_id, operation=None, outcome=None, status="performed"):
    knowledge = []
    nodes = []
    transitions = []
    edges = []
    if operation:
        knowledge.append({
            "knowledge_id": "K1", "kind": "action", "action_status": status,
            "semantic_frame": {"statements": [{"predicate": operation}]},
        })
        nodes.append({"id": "O1", "knowledge_id": "K1"})
    if outcome:
        knowledge.append({
            "knowledge_id": "K2", "kind": "state", "action_status": None,
            "semantic_frame": {"statements": [{"predicate": outcome}]},
        })
        nodes.append({"id": "O2", "knowledge_id": "K2"})
    if operation and outcome:
        transitions.append({"id": "T1", "sources": ["O1"], "target": "O2"})
        edges.append({"source": "O1", "target": "O2"})
    return {
        "article_id": article_id,
        "run_id": f"run-{article_id}",
        "source": {"sha256": f"sha-{article_id}", "text": "source"},
        "graph": {"schema_version": 6, "knowledge": knowledge, "nodes": nodes,
                  "edges": edges, "transitions": transitions},
    }


def _record(article_id, family, graph_links, operations=None, cooccurrence=None):
    return {
        "article_id": article_id,
        "run_id": f"run-{article_id}",
        "source_sha256": f"sha-{article_id}",
        "support_family": family,
        "operation_families": operations or ["statistical_analysis"],
        "outcome_families": [],
        "graph_links": graph_links,
        "cooccurrence_links": cooccurrence or graph_links,
        "direct_links": [],
        "coverage": {},
    }


def test_operation_taxonomy_preserves_distinct_research_operations():
    assert classify_operation("fit Cox proportional-hazards model") == "statistical_analysis"
    assert classify_operation("performed recruitment and follow-up") == "cohort_design_and_followup"
    assert classify_operation("administer treatment") == "experimental_intervention_or_assay"
    assert classify_operation("unresolved research task") is None
    assert classify_outcome("association not statistically detected") == "reported_association"
    assert classify_outcome("reported cohort incidence") == "reported_frequency"


def test_only_performed_actions_can_license_a_transfer_pair():
    snapshot = _snapshot("target", "estimate incidence rate", "reported cohort incidence", "planned")
    row = extract_article(snapshot)
    assert row["operation_families"] == []
    assert row["graph_links"] == []
    assert row["coverage"]["action_blocks_performed"] == 0


def test_extracts_direct_graph_pair_and_audits_unmapped_predicates():
    row = extract_article(_snapshot("target", "estimate incidence rate", "reported cohort incidence"))
    assert row["graph_links"] == [["statistical_analysis", "reported_frequency"]]
    assert row["cooccurrence_links"] == row["graph_links"]
    assert row["coverage"]["action_statement_coverage"] == 1
    assert row["coverage"]["state_predicates_checked"] == 1
    assert row["coverage"]["state_predicates_classified_as_reported_outcome"] == 1
    assert row["coverage"]["reported_outcome_category_counts"] == {"reported_frequency": 1}


def test_support_is_counted_by_distinct_publication_family():
    pair = ["statistical_analysis", "reported_frequency"]
    target = _record("target", "target", [], cooccurrence=[])
    same_family_rows = [
        _record("train-a", "one-study", [pair]),
        _record("train-b", "one-study", [pair]),
        target,
    ]
    sealed = seal_predictions(same_family_rows, minimum_support=2)
    target_fold = next(f for f in sealed["folds"] if f["target_article_id"] == "target")
    assert target_fold["predictions"]["graph"] == []

    independent_rows = [
        _record("train-a", "study-a", [pair]),
        _record("train-b", "study-b", [pair]),
        target,
    ]
    sealed = seal_predictions(independent_rows, minimum_support=2)
    target_fold = next(f for f in sealed["folds"] if f["target_article_id"] == "target")
    assert target_fold["predictions"]["graph"] == [pair]


def test_target_outcomes_do_not_change_its_frozen_forecast():
    pair = ["statistical_analysis", "reported_frequency"]
    rows = [
        _record("train-a", "study-a", [pair]),
        _record("train-b", "study-b", [pair]),
        _record("target", "target", [], cooccurrence=[]),
    ]
    before = seal_predictions(rows, minimum_support=2)
    changed = deepcopy(rows)
    changed[-1]["graph_links"] = [["measurement_or_assessment", "reported_limit"]]
    changed[-1]["outcome_families"] = ["reported_limit"]
    after = seal_predictions(changed, minimum_support=2)
    target_before = next(f for f in before["folds"]
                         if f["target_article_id"] == "target")
    target_after = next(f for f in after["folds"]
                        if f["target_article_id"] == "target")
    assert target_before == target_after
    assert score_predictions(changed, after)["aggregate"]["graph"]["hits"] == 0


def test_permutation_preserves_each_article_operation_and_outcome_marginals():
    row = _record("a", "a", [], operations=["measurement_or_assessment", "statistical_analysis"])
    row["direct_links"] = [
        {"operation_family": "measurement_or_assessment", "outcome_family": "reported_frequency"},
        {"operation_family": "statistical_analysis", "outcome_family": "reported_limit"},
    ]
    permuted = _permuted_records([row], seed=7)[0]
    assert sorted(pair[0] for pair in permuted["graph_links"]) == [
        "measurement_or_assessment", "statistical_analysis"
    ]
    assert sorted(link["outcome_family"] for link in permuted["direct_links"]) == [
        "reported_frequency", "reported_limit"
    ]
    assert len(permuted["graph_links"]) == 2


def test_tied_ranks_use_fractional_expected_hits_not_lexical_order():
    ranked = [
        {"pair": ["analysis", "common"], "distinct_source_families": 2},
        {"pair": ["analysis", "actual"], "distinct_source_families": 1},
        {"pair": ["analysis", "other"], "distinct_source_families": 1},
    ]

    hits, slots = _expected_hits_at_k(
        ranked, {("analysis", "actual")}, k=2)

    assert hits == 0.5
    assert slots == 2


def test_sealed_ranking_uses_training_outcomes_and_target_operations_only():
    frequency = ["statistical_analysis", "reported_frequency"]
    parameter = ["statistical_analysis", "reported_model_parameter"]
    target_only = ["statistical_analysis", "reported_limit"]
    rows = [
        _record("train-frequency", "study-a", [frequency]),
        _record("train-parameter", "study-b", [parameter]),
        _record("target", "target", [target_only]),
    ]
    rows[0]["outcome_families"] = ["reported_frequency"]
    rows[1]["outcome_families"] = ["reported_model_parameter"]
    rows[2]["outcome_families"] = ["reported_limit"]

    sealed = seal_predictions(rows, minimum_support=1)
    target_fold = next(f for f in sealed["folds"] if f["target_article_id"] == "target")

    ranked_pairs = {tuple(item["pair"])
                    for item in target_fold["ranked_candidates"]["graph"]}
    assert ranked_pairs == {tuple(frequency), tuple(parameter)}
    assert tuple(target_only) not in ranked_pairs
    assert sealed["target_outcomes_or_dependencies_used"] is False


def test_scoring_reports_equal_budget_ranked_metrics():
    frequent = ["statistical_analysis", "reported_frequency"]
    parameter = ["statistical_analysis", "reported_model_parameter"]
    rows = [
        _record("train-frequency", "study-a", [frequent]),
        _record("train-parameter", "study-b", [parameter]),
        _record("target", "target", [frequent]),
    ]
    rows[0]["outcome_families"] = ["reported_frequency"]
    rows[1]["outcome_families"] = ["reported_model_parameter"]
    rows[2]["outcome_families"] = ["reported_frequency"]

    sealed = seal_predictions(rows, minimum_support=1)
    permuted = seal_permuted_predictions(rows, minimum_support=1, seeds=(3, 7))
    scored = score_predictions(rows, sealed, permuted)
    target_fold = next(f for f in scored["folds"] if f["target_article_id"] == "target")

    assert target_fold["ranked_scores"]["graph"]["1"]["expected_hits"] == 0.5
    assert scored["ranked_aggregate"]["1"]["graph"]["candidate_slots"] == 3
    assert set(scored["permuted_control"]["ranked_top_k"]) == {"1", "3", "5", "10"}
    assert scored["permuted_control"]["unique_ranked_profiles"] >= 1

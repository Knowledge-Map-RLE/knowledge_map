from domain.action_result_semantic_resolution import (
    LEVELS, _claim_signature, extract_article, score_forecasts, seal_forecasts,
)


def _statement(*, roles=None, attributes=None, modality=None, negated=False):
    return {
        "predicate": "incidence rate",
        "roles": roles or [{"role": "population"}, {"role": "outcome"}],
        "negated": negated,
        "quantifier": None,
        "modality": modality,
        "conditions": ["observational cohort"],
        "temporal_context": "follow-up",
        "qualifiers": {"attributes": attributes or []},
    }


def _knowledge(statement):
    return {
        "knowledge_id": "result-1",
        "kind": "state",
        "knowledge_kind": "observation",
        "semantic_frame": {"logic": "single", "statements": [statement]},
    }


def _record(article_id, operation, signature):
    pair = {"operation_family": operation, "outcome_signature": list(signature)}
    return {
        "article_id": article_id,
        "run_id": f"run-{article_id}",
        "support_family": f"publication-{article_id}",
        "graph_pairs": {level: [pair] for level in LEVELS},
        "without_dependencies_pairs": {level: [pair] for level in LEVELS},
        "target_pairs": {level: [pair] for level in LEVELS},
    }


def test_signature_adds_roles_and_guards_without_copying_numeric_values() -> None:
    item = _knowledge(_statement(attributes=[
        {"name": "rate", "value": 3.79, "unit": "per 100 person-years"},
    ]))
    changed_value = _knowledge(_statement(attributes=[
        {"name": "rate", "value": 8.12, "unit": "per 100 person-years"},
    ]))

    family = _claim_signature(item, item["semantic_frame"]["statements"][0], 0)
    predicate = _claim_signature(item, item["semantic_frame"]["statements"][0], 1)
    roles = _claim_signature(item, item["semantic_frame"]["statements"][0], 2)
    qualified = _claim_signature(item, item["semantic_frame"]["statements"][0], 4)
    changed_qualified = _claim_signature(
        changed_value, changed_value["semantic_frame"]["statements"][0], 4)

    assert family[0] == "reported_frequency"
    assert predicate[:len(family)] == family
    assert roles[:len(predicate)] == predicate
    assert roles != predicate
    assert qualified == changed_qualified
    assert qualified[-3] == (("rate", "per 100 person-years"),)


def test_extract_article_projects_direct_action_result_transition() -> None:
    action = {
        "knowledge_id": "action-1", "kind": "action", "action_status": "performed",
        "semantic_frame": {"statements": [{"predicate": "fit cox proportional-hazards model"}]},
    }
    outcome = _knowledge(_statement())
    snapshot = {
        "article_id": "article-a", "run_id": "run-a",
        "graph": {
            "schema_version": 6,
            "knowledge": [action, outcome],
            "nodes": [
                {"id": "action-occurrence", "knowledge_id": "action-1"},
                {"id": "result-occurrence", "knowledge_id": "result-1"},
            ],
            "edges": [],
            "transitions": [{
                "sources": ["action-occurrence"], "target": "result-occurrence",
            }],
        },
    }

    row = extract_article(snapshot, "publication-a")

    assert row["graph_pairs"][0] == row["without_dependencies_pairs"][0]
    assert row["target_pairs"][0] == row["graph_pairs"][0]
    assert row["graph_pairs"][2][0]["outcome_signature"][:2] == [
        "reported_frequency", "incidence rate",
    ]


def test_forecast_excludes_citers_before_support_and_scores_after_sealing() -> None:
    signature = ["reported_frequency", "incidence rate"]
    records = [
        _record("source-a", "statistical_analysis", signature),
        _record("source-b", "statistical_analysis", signature),
        _record("citer", "experimental_assay", signature),
        _record("target", "statistical_analysis", signature),
    ]
    exclusions = {row["article_id"]: [] for row in records}
    exclusions["target"] = [{"citing_article_id": "citer"}]

    sealed = seal_forecasts(records, exclusions, minimum_support=2)
    target_fold = next(row for row in sealed["folds"]
                       if row["target_article_id"] == "target")
    scores = score_forecasts(records, sealed)
    scored_target = next(row for row in scores["folds"]
                         if row["target_article_id"] == "target")

    assert target_fold["training_article_ids"] == ["source-a", "source-b"]
    assert target_fold["predictions"]["graph"][0][0]["operation_family"] == \
        "statistical_analysis"
    assert scored_target["levels"][0]["graph"]["hits"] == 1
    assert sealed["target_operation_families_used"] is False
    assert sealed["target_outcomes_or_dependencies_used"] is False

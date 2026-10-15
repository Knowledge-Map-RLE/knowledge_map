from domain.cohort_operation_transfer import (
    evaluate_lopo,
    forecast_for_known_operations,
    learn_links,
    operation_families,
    output_families,
    score,
)


def test_explicit_operation_and_result_aliases_are_routed():
    operation = {
        "kind": "action",
        "semantic_frame": {"statements": [{"predicate": "fit Cox proportional-hazards model"}]},
    }
    result = {
        "kind": "state",
        "semantic_frame": {"statements": [{"predicate": "estimated association",
                                             "qualifiers": {"attributes": [{"name": "hazard_ratio"}]}}]},
    }

    assert operation_families(operation) == {"survival_model_fitting"}
    assert output_families(result) == {"reported_model_parameter"}
    qualitative = {
        "kind": "state",
        "semantic_frame": {"statements": [{"predicate": "estimated association",
                                             "qualifiers": {"attributes": []}}]},
    }
    assert output_families(qualitative) == {"reported_association"}
    direct_parameter = {
        "kind": "state",
        "semantic_frame": {"statements": [{"predicate": "adjusted hazard ratio",
                                             "qualifiers": {"attributes": []}}]},
    }
    assert output_families(direct_parameter) == {"reported_model_parameter"}
    person_time = {
        "kind": "action",
        "semantic_frame": {"statements": [{"predicate": "calculate person-time"}]},
    }
    assert operation_families(person_time) == {"person_time_calculation"}
    legacy_incidence = {
        "kind": "action",
        "semantic_frame": {"statements": [{"predicate": "incidence calculation method"}]},
    }
    legacy_cox = {
        "kind": "action",
        "semantic_frame": {"statements": [{"predicate": "Cox risk-factor analysis"}]},
    }
    time_to_decline_cox = {
        "kind": "action",
        "semantic_frame": {"statements": [{"predicate": "fit time-to-decline models"}]},
    }
    assert operation_families(legacy_incidence) == {"incidence_estimation"}
    assert operation_families(legacy_cox) == {"survival_model_fitting"}
    assert operation_families(time_to_decline_cox) == {"survival_model_fitting"}


def test_link_support_counts_distinct_publications_not_within_map_repeats():
    learned = learn_links({
        "paper-a": [["incidence_estimation", "reported_frequency"]] * 12,
        "paper-b": [["incidence_estimation", "reported_frequency"]],
        "paper-c": [["survival_model_fitting", "reported_model_parameter"]],
    }, minimum_support=2)

    assert learned == {("incidence_estimation", "reported_frequency")}


def test_scoring_keeps_direction_of_operation_result_pair():
    result = score(
        {("incidence_estimation", "reported_frequency"),
         ("survival_model_fitting", "reported_frequency")},
        {("incidence_estimation", "reported_frequency"),
         ("survival_model_fitting", "reported_model_parameter")},
    )

    assert result["hits"] == 1
    assert result["precision"] == 0.5
    assert result["recall"] == 0.5
    assert result["extra_pairs"] == [["survival_model_fitting", "reported_frequency"]]
    assert result["missed_pairs"] == [["survival_model_fitting", "reported_model_parameter"]]


def test_method_conditioned_lopo_uses_target_operation_as_input_and_hides_outputs():
    common = {
        "operator_families": ["incidence_estimation"],
        "graph_links": [["incidence_estimation", "reported_frequency"]],
        "cooccurrence_links": [["incidence_estimation", "reported_frequency"],
                               ["incidence_estimation", "reported_model_parameter"]],
        "graph_evidence": {},
        "run_id": "test-run",
    }
    rows = [
        {"article_id": "paper-a", **common},
        {"article_id": "paper-b", **common},
        {"article_id": "paper-c", "operator_families": [], "graph_links": [],
         "cooccurrence_links": [], "graph_evidence": {}, "run_id": "test-run"},
    ]

    result = evaluate_lopo(rows, minimum_support=1)

    assert result["aggregate"]["dependency_edges"]["precision"] == 1.0
    assert result["aggregate"]["same_article_cooccurrence"]["precision"] == 0.5
    ineligible = next(row for row in result["folds"] if row["target_article_id"] == "paper-c")
    assert ineligible["scored_for_operator_conditioned_forecast"] is False
    assert ineligible["graph_training_links"] == []


def test_sealed_forecast_uses_only_training_links_and_known_target_methods():
    training = {
        "paper-a": {"graph_links": [["survival_model_fitting", "reported_model_parameter"]],
                    "cooccurrence_links": [["survival_model_fitting", "reported_model_parameter"],
                                           ["survival_model_fitting", "reported_association"]]},
        "paper-b": {"graph_links": [["survival_model_fitting", "reported_model_parameter"]],
                    "cooccurrence_links": [["survival_model_fitting", "reported_model_parameter"],
                                           ["survival_model_fitting", "reported_association"]]},
    }

    forecast = forecast_for_known_operations(training, {"survival_model_fitting"}, minimum_support=2)

    assert forecast["dependency_edges"] == [["survival_model_fitting", "reported_model_parameter"]]
    assert forecast["same_article_cooccurrence"] == [
        ["survival_model_fitting", "reported_association"],
        ["survival_model_fitting", "reported_model_parameter"],
    ]

from domain.cohort_operation_result_transfer import filter_result_usage
from domain.sealed_operation_result_forecast import build_fold_prediction


def test_result_transfer_excludes_method_and_premise_links():
    links = [
        ["survival_model_fitting", "reported_model_parameter"],
        ["incidence_estimation", "reported_frequency"],
    ]
    evidence = {
        "survival_model_fitting|reported_model_parameter": [
            {"transition_id": "t-method", "usage": "method"},
            {"transition_id": "t-result", "usage": "result"},
        ],
        "incidence_estimation|reported_frequency": [
            {"transition_id": "t-premise", "usage": "premise"},
        ],
    }

    filtered_links, filtered_evidence = filter_result_usage(links, evidence)

    assert filtered_links == [["survival_model_fitting", "reported_model_parameter"]]
    assert filtered_evidence == {
        "survival_model_fitting|reported_model_parameter": [
            {"transition_id": "t-result", "usage": "result"}
        ]
    }
    assert evidence["survival_model_fitting|reported_model_parameter"][0]["usage"] == "method"


def test_result_transfer_retains_only_explicit_result_basis():
    links, evidence = filter_result_usage(
        [["incidence_estimation", "reported_frequency"]],
        {"incidence_estimation|reported_frequency": [{"transition_id": "t1", "usage": "result"}]},
    )

    assert links == [["incidence_estimation", "reported_frequency"]]
    assert evidence["incidence_estimation|reported_frequency"][0]["transition_id"] == "t1"


def test_sealed_prediction_keeps_all_usage_and_result_usage_modes_separate():
    fold = {
        "target": {"article_id": "target", "map_sha256": "map", "source_sha256": "source",
                   "run_id": "run", "operation_families": ["survival_model_fitting"]},
        "training_sources": [{"article_id": "a"}, {"article_id": "b"}],
    }
    rows = {
        "a": {"legacy_graph_links": [["survival_model_fitting", "reported_model_parameter"],
                                      ["survival_model_fitting", "reported_association"]],
              "graph_links": [["survival_model_fitting", "reported_model_parameter"]],
              "cooccurrence_links": [["survival_model_fitting", "reported_model_parameter"],
                                     ["survival_model_fitting", "reported_association"]]},
        "b": {"legacy_graph_links": [["survival_model_fitting", "reported_model_parameter"],
                                      ["survival_model_fitting", "reported_association"]],
              "graph_links": [["survival_model_fitting", "reported_model_parameter"]],
              "cooccurrence_links": [["survival_model_fitting", "reported_model_parameter"],
                                     ["survival_model_fitting", "reported_association"]]},
    }

    prediction = build_fold_prediction(fold, rows, minimum_support=2)

    assert {row["output_family"] for row in prediction["forecasts"]["dependency_edges_all_usage"]} == {
        "reported_model_parameter", "reported_association"
    }
    assert {row["output_family"] for row in prediction["forecasts"]["dependency_edges_result_usage"]} == {
        "reported_model_parameter"
    }
    assert len(prediction["forecasts"]["same_article_cooccurrence"]) == 2
    assert prediction["target_outputs_or_edges_available_to_forecaster"] is False

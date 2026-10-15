from domain.sealed_operation_forecast import build_fold_prediction


def test_sealed_fold_only_uses_training_edges_and_target_operation_context():
    fold_input = {
        "target": {"article_id": "target", "map_sha256": "map", "source_sha256": "source",
                   "run_id": "run", "operation_families": ["survival_model_fitting"]},
        "training_sources": [{"article_id": "a"}, {"article_id": "b"}],
    }
    training = {
        "a": {"graph_links": [["survival_model_fitting", "reported_model_parameter"]],
              "cooccurrence_links": [["survival_model_fitting", "reported_model_parameter"],
                                     ["survival_model_fitting", "reported_association"]]},
        "b": {"graph_links": [["survival_model_fitting", "reported_model_parameter"]],
              "cooccurrence_links": [["survival_model_fitting", "reported_model_parameter"],
                                     ["survival_model_fitting", "reported_association"]]},
    }

    prediction = build_fold_prediction(fold_input, training, minimum_support=2)

    assert prediction["forecasts"]["dependency_edges"] == [
        {"operation_family": "survival_model_fitting", "output_family": "reported_model_parameter",
         "support_count": 2, "support_sources": ["a", "b"]}
    ]
    assert len(prediction["forecasts"]["same_article_cooccurrence"]) == 2
    assert prediction["target_outputs_or_edges_available_to_forecaster"] is False


def test_sealed_fold_rejects_target_in_training_and_unregistered_operations():
    fold_input = {
        "target": {"article_id": "target", "map_sha256": "map", "source_sha256": "source",
                   "run_id": "run", "operation_families": ["survival_model_fitting"]},
        "training_sources": [{"article_id": "target"}],
    }

    try:
        build_fold_prediction(fold_input, {"target": {"graph_links": [], "cooccurrence_links": []}})
    except ValueError as exc:
        assert "Целевая статья" in str(exc)
    else:
        raise AssertionError("Цель не должна попадать в собственное обучение")

    fold_input["training_sources"] = []
    fold_input["target"]["operation_families"] = ["invented_operation"]
    try:
        build_fold_prediction(fold_input, {})
    except ValueError as exc:
        assert "Неизвестный" in str(exc)
    else:
        raise AssertionError("Неизвестные операции должны отклоняться")

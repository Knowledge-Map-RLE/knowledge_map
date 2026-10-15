"""Запечатанный перенос категорий результата с отдельной фильтрацией usage=result."""
from __future__ import annotations

from domain.article_maps import require
from domain.cohort_operation_transfer import OPERATOR_FAMILIES
from domain.sealed_operation_forecast import _supported_pairs

VERSION = "sealed-cohort-operation-result-usage-lopo-1"


def build_fold_prediction(fold_input: dict, training_rows: dict[str, dict],
                          minimum_support: int = 2) -> dict:
    require(type(minimum_support) is int and minimum_support >= 1,
            "Минимальная поддержка должна быть положительной")
    target = fold_input["target"]
    target_id = target["article_id"]
    operations = set(target["operation_families"])
    expected_training = {item["article_id"] for item in fold_input["training_sources"]}
    require(bool(operations) and operations <= OPERATOR_FAMILIES, "Неизвестный или пустой тип операции")
    require(target_id not in expected_training and set(training_rows) == expected_training,
            "Обучающие карты не совпадают с запечатанным фолдом")

    all_usage_rows = {
        article_id: {"graph_links": row["legacy_graph_links"]}
        for article_id, row in training_rows.items()
    }
    result_usage_rows = {
        article_id: {"graph_links": row["graph_links"]}
        for article_id, row in training_rows.items()
    }
    cooccurrence_rows = {
        article_id: {"cooccurrence_links": row["cooccurrence_links"]}
        for article_id, row in training_rows.items()
    }
    return {
        "protocol": VERSION,
        "target_article_id": target_id,
        "target_map_sha256": target["map_sha256"],
        "target_source_sha256": target["source_sha256"],
        "target_run_id": target["run_id"],
        "known_operation_families": sorted(operations),
        "training_source_ids": sorted(training_rows),
        "training_source_count": len(training_rows),
        "minimum_publication_support": minimum_support,
        "transition_usage_filter": "result",
        "forecasts": {
            "same_article_cooccurrence": _supported_pairs(
                cooccurrence_rows, "cooccurrence_links", operations, minimum_support),
            "dependency_edges_all_usage": _supported_pairs(
                all_usage_rows, "graph_links", operations, minimum_support),
            "dependency_edges_result_usage": _supported_pairs(
                result_usage_rows, "graph_links", operations, minimum_support),
        },
        "target_outputs_or_edges_available_to_forecaster": False,
        "network_disabled": True,
        "external_llm_calls": 0,
        "local_llm_calls": 0,
        "embedding_calls": 0,
        "scientific_fact_forecast": False,
    }

"""Доменные правила прогноза категорий результатов по запечатанному срезу."""
from __future__ import annotations

from domain.article_maps import require
from domain.cohort_operation_transfer import OPERATOR_FAMILIES

VERSION = "sealed-cohort-operation-lopo-1"


def _supported_pairs(training_rows: dict[str, dict], field: str,
                     known_operations: set[str], minimum_support: int) -> list[dict]:
    support: dict[tuple[str, str], set[str]] = {}
    for article_id, row in training_rows.items():
        for raw_pair in row[field]:
            pair = tuple(raw_pair)
            if len(pair) == 2 and pair[0] in known_operations:
                support.setdefault(pair, set()).add(article_id)
    return [
        {"operation_family": pair[0], "output_family": pair[1],
         "support_count": len(source_ids), "support_sources": sorted(source_ids)}
        for pair, source_ids in sorted(support.items())
        if len(source_ids) >= minimum_support
    ]


def build_fold_prediction(fold_input: dict, training_rows: dict[str, dict],
                          minimum_support: int = 2) -> dict:
    """Строит кандидатов только из контекста метода и карт обучения данного фолда."""
    require(minimum_support >= 1, "Минимальная поддержка должна быть положительной")
    target = fold_input["target"]
    target_id = target["article_id"]
    operation_families = set(target["operation_families"])
    require(bool(operation_families) and operation_families <= OPERATOR_FAMILIES,
            "Неизвестный или пустой целевой контекст методов")
    expected_training = {item["article_id"] for item in fold_input["training_sources"]}
    require(target_id not in expected_training, "Целевая статья попала в список обучения")
    require(set(training_rows) == expected_training, "Загруженные карты не совпадают с обучающим фолдом")

    return {
        "protocol": VERSION,
        "target_article_id": target_id,
        "target_map_sha256": target["map_sha256"],
        "target_source_sha256": target["source_sha256"],
        "target_run_id": target["run_id"],
        "known_operation_families": sorted(operation_families),
        "training_source_ids": sorted(training_rows),
        "training_source_count": len(training_rows),
        "minimum_publication_support": minimum_support,
        "forecasts": {
            "same_article_cooccurrence": _supported_pairs(
                training_rows, "cooccurrence_links", operation_families, minimum_support),
            "dependency_edges": _supported_pairs(
                training_rows, "graph_links", operation_families, minimum_support),
        },
        "target_outputs_or_edges_available_to_forecaster": False,
        "network_disabled": True,
        "external_llm_calls": 0,
        "local_llm_calls": 0,
        "embedding_calls": 0,
        "scientific_fact_forecast": False,
    }

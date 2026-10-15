"""Запечатывает прогноз категории результата GEMS до чтения выходов карты."""
from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

from domain.cohort_operation_transfer import (
    VERSION,
    extract_map,
    operation_families,
)
from domain.article_maps import require
from infrastructure.immutable_files import write_immutable
from tools.run_free_prediction import disable_network

ROOT = Path(r"D:\Knowledge_Map")
SOURCE_MANIFEST = ROOT / "eval/whole_map_forecast/research-corpus-extension-v1/cohort-operation-transfer-v7/source-manifest.json"
OUTPUT = ROOT / "eval/whole_map_forecast/cohort_operation_prediction/gems-cox-sealed-v1"
TARGET_ID = "PMC6218168"
MINIMUM_SUPPORT = 2


def _sha(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def _json_bytes(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")


def _supported_pairs(training_rows: dict[str, dict], field: str,
                     known_operations: set[str]) -> list[dict]:
    support: dict[tuple[str, str], set[str]] = {}
    for article_id, row in training_rows.items():
        for raw_pair in row[field]:
            pair = tuple(raw_pair)
            if pair[0] in known_operations:
                support.setdefault(pair, set()).add(article_id)
    return [
        {"operation_family": pair[0], "output_family": pair[1],
         "support_count": len(sources), "support_sources": sorted(sources)}
        for pair, sources in sorted(support.items()) if len(sources) >= MINIMUM_SUPPORT
    ]


def main() -> None:
    disable_network()
    manifest = json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))
    source_rows = manifest["sources"]
    target_row = next(row for row in source_rows if row["article_id"] == TARGET_ID)
    target_path = Path(target_row["map_path"])
    target_raw = target_path.read_bytes()
    require(_sha(target_raw) == target_row["map_sha256"], "Отложенная карта изменилась после заморозки корпуса")
    target_snapshot = json.loads(target_raw)
    require(target_snapshot["article_id"] == TARGET_ID and target_snapshot["source"]["sha256"] == target_row["source_sha256"],
            "Идентичность целевой статьи изменилась")
    require(target_snapshot["pipeline_id"] == "text_reified" and target_snapshot["graph_schema_version"] == 6,
            "Для прогноза нужна прямая карта схемы 6")

    # Целевая карта читается только по узлам методов; её результаты и переходы к результатам не извлекаются.
    target_actions = []
    for item in target_snapshot["graph"]["knowledge"]:
        if item["kind"] != "action":
            continue
        families = operation_families(item)
        if families:
            target_actions.append({"knowledge_id": item["knowledge_id"],
                                   "operation_families": sorted(families),
                                   "source_spans": item["provenance"]["source_spans"]})
    known_operations = {family for item in target_actions for family in item["operation_families"]}
    require(bool(known_operations), "У целевой статьи нет операции из зафиксированного словаря")

    training_rows = {}
    for row in source_rows:
        if row["article_id"] == TARGET_ID:
            continue
        raw = Path(row["map_path"]).read_bytes()
        require(_sha(raw) == row["map_sha256"], "Обучающая карта изменилась после заморозки корпуса")
        snapshot = json.loads(raw)
        extracted = extract_map(snapshot)
        require(extracted["article_id"] == row["article_id"], "Идентификатор источника изменился")
        training_rows[row["article_id"]] = extracted
    require(TARGET_ID not in training_rows and len(training_rows) == len(source_rows) - 1,
            "Отложенная карта попала в обучающий корпус")

    predictions = {
        "protocol": "sealed-method-conditioned-result-category-1",
        "inference_version": VERSION,
        "target_article_id": TARGET_ID,
        "target_map_sha256": target_row["map_sha256"],
        "target_source_sha256": target_row["source_sha256"],
        "target_method_context": target_actions,
        "target_output_knowledge_read_for_prediction": False,
        "target_dependency_edges_read_for_prediction": False,
        "training_source_ids": sorted(training_rows),
        "training_source_count": len(training_rows),
        "minimum_publication_support": MINIMUM_SUPPORT,
        "forecasts": {
            "same_article_cooccurrence": _supported_pairs(training_rows, "cooccurrence_links", known_operations),
            "dependency_edges": _supported_pairs(training_rows, "graph_links", known_operations),
        },
        "network_disabled": True,
        "external_llm_calls": 0,
        "local_llm_calls": 0,
        "embedding_calls": 0,
        "scientific_fact_forecast": False,
    }
    prediction_bytes = _json_bytes(predictions)
    run_id = _sha(prediction_bytes)[:32]
    run_root = OUTPUT / "runs" / run_id
    write_immutable(run_root / "sealed-prediction.json", prediction_bytes)
    seal = {
        "run_id": run_id,
        "prediction_sha256": _sha(prediction_bytes),
        "target_map_sha256": target_row["map_sha256"],
        "target_output_knowledge_read_for_prediction": False,
        "target_dependency_edges_read_for_prediction": False,
        "sealed": True,
    }
    write_immutable(run_root / "seal.json", _json_bytes(seal))
    print(json.dumps({"run_id": run_id, "sealed_prediction": str(run_root / "sealed-prediction.json"),
                      "seal": str(run_root / "seal.json"), "target_operations": sorted(known_operations),
                      "training_source_count": len(training_rows), "network_disabled": True,
                      "model_calls": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()

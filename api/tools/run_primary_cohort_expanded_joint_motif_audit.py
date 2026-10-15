"""Добавляет две новые ручные когорты к замороженному аудиту мотивов без AI."""
from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

from domain.article_maps import require
from infrastructure.immutable_files import write_immutable
from tools.audit_joint_operator_patterns import run as run_audit
from tools.run_free_prediction import disable_network


ROOT = Path(__file__).resolve().parents[2]
BASE_MANIFEST = ROOT / "eval/whole_map_forecast/research-corpus-extension-v1/luck-joint-motif-v2/source-manifest.json"
OUTPUT = ROOT / "eval/whole_map_forecast/research-corpus-extension-v1/primary-cohort-joint-motif-v3"
TARGET_SHA256 = "f7df96ff746be4a60a6930ff2c5c25435725d0591dfe1f492259624b2d7c0bc8"
NEW_RUNS = {
    "roberts2012": "5425d208-b41c-5247-954c-bda8c53f2d33",
    "katz2012": "b8b1f3a6-bcc7-55ca-a9e2-181211d5df0e",
}


def sha(data: bytes) -> str:
    return sha256(data).hexdigest()


def main() -> None:
    disable_network()
    manifest = json.loads(BASE_MANIFEST.read_text(encoding="utf-8"))
    require(manifest.get("version") == "joint-motif-explicit-inputs-1", "Нужен утверждённый формат явного манифеста")
    require(len(manifest.get("sources", [])) == 14, "Исходный сравнимый корпус должен содержать 14 карт")
    require(all(row["source_sha256"] != TARGET_SHA256 for row in manifest["sources"]),
            "Цель PMC10000452 уже присутствует в базовом манифесте")
    existing = {row["article_id"] for row in manifest["sources"]}
    require(not (existing & set(NEW_RUNS)), "Новые когорты уже присутствуют в базовом манифесте")

    added = []
    for article_id, run_id in NEW_RUNS.items():
        run_dir = ROOT / "eval/whole_map_forecast/primary-cohort-expansion-codex-v1/runs" / run_id
        map_path = run_dir / "map.json"
        raw_map = map_path.read_bytes()
        snapshot = json.loads(raw_map)
        review = json.loads((run_dir / "source-review.json").read_text(encoding="utf-8"))
        validation = json.loads((run_dir / "validation.json").read_text(encoding="utf-8"))
        require(snapshot["article_id"] == article_id and snapshot["run_id"] == run_id,
                f"Идентификатор карты отличается: {article_id}")
        require(snapshot["pipeline_id"] == "text_reified" and snapshot["graph_schema_version"] == 6,
                f"Неподходящая схема: {article_id}")
        require(snapshot["source"]["sha256"] != TARGET_SHA256, "Целевая статья не допускается в обучение")
        require(review["training_only"] is True and review["prior_source_exposure"] is True,
                f"Просмотренная статья должна быть помечена только для обучения: {article_id}")
        require(review["external_llm_calls"] == review["local_llm_calls"] == 0,
                f"Обнаружен модельный вызов: {article_id}")
        require(validation["contract"] == validation["dag"] == validation["provenance"] == "passed",
                f"Проверка карты не прошла: {article_id}")
        row = {
            "article_id": article_id,
            "run_id": run_id,
            "path": str(map_path),
            "file_sha256": sha(raw_map),
            "source_sha256": snapshot["source"]["sha256"],
            "family": f"publication:{article_id}",
        }
        manifest["sources"].append(row)
        added.append({**row, "knowledge_count": len(snapshot["graph"]["knowledge"]),
                      "transition_count": len(snapshot["graph"]["transitions"]),
                      "source_unit_count": validation["coverage_units"]})

    require(len(manifest["sources"]) == 16, "После добавления ожидалось 16 карт")
    require(len({row["article_id"] for row in manifest["sources"]}) == 16, "В корпусе есть дубли публикаций")
    manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
    write_immutable(OUTPUT / "source-manifest.json", manifest_bytes)
    preparation = {
        "protocol": "joint-author-motif-census-primary-cohort-expansion-1",
        "base_manifest_sha256": sha(BASE_MANIFEST.read_bytes()),
        "expanded_manifest_sha256": sha(manifest_bytes),
        "added_sources": added,
        "held_out_target_source_sha256": TARGET_SHA256,
        "all_new_maps_previously_exposed": True,
        "new_maps_training_only": True,
        "model_calls": 0,
        "network_disabled": True,
        "expert_validated": False,
    }
    write_immutable(OUTPUT / "preparation.json", json.dumps(preparation, ensure_ascii=False, indent=2).encode("utf-8"))
    result = run_audit(OUTPUT / "source-manifest.json", OUTPUT, TARGET_SHA256)
    print(result)


if __name__ == "__main__":
    main()

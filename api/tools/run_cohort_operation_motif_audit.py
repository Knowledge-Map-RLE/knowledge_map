"""Проверяет перенос операционных мотивов в расширенных картах трёх когорт."""
from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

from domain.article_maps import require
from domain.operator_pattern_forecast import validate_map_snapshot
from infrastructure.immutable_files import write_immutable
from tools.audit_joint_operator_patterns import run as run_audit
from tools.run_free_prediction import disable_network


ROOT = Path(__file__).resolve().parents[2]
BASE_MANIFEST = ROOT / "eval/whole_map_forecast/research-corpus-extension-v1/primary-cohort-joint-motif-v3/source-manifest.json"
OUTPUT = ROOT / "eval/whole_map_forecast/research-corpus-extension-v1/cohort-operation-motif-v2"
TARGET_SHA256 = "f7df96ff746be4a60a6930ff2c5c25435725d0591dfe1f492259624b2d7c0bc8"
REPLACEMENTS = {
    "roberts2012": ROOT / "eval/whole_map_forecast/primary-cohort-expansion-codex-v1/runs/4a2c440d-9b7d-5489-94fa-2612954f36e0/map.json",
    "katz2012": ROOT / "eval/whole_map_forecast/primary-cohort-expansion-codex-v1/runs/7cc9bb9c-3699-5aea-a280-2bc122733690/map.json",
    "manly2008": ROOT / "eval/whole_map_forecast/manly-complete-map-v1/combined-draft/7be503af-4eb9-5fef-8dd2-4d550e28827f/map.json",
}


def sha(data: bytes) -> str:
    return sha256(data).hexdigest()


def build_manifest() -> tuple[dict, dict]:
    base = json.loads(BASE_MANIFEST.read_text(encoding="utf-8"))
    require(base.get("version") == "joint-motif-explicit-inputs-1", "Нужен явный исходный манифест")
    require(len(base.get("sources", [])) == 16, "Ожидался замороженный корпус из 16 статей")
    require(all(row["source_sha256"] != TARGET_SHA256 for row in base["sources"]),
            "Целевая PMC10000452 не должна входить в обучение")
    require(set(REPLACEMENTS) <= {row["article_id"] for row in base["sources"]},
            "Заменяемая статья отсутствует в исходном корпусе")

    sources = []
    replacements = []
    for base_row in base["sources"]:
        map_path = REPLACEMENTS.get(base_row["article_id"], Path(base_row["path"]))
        raw = map_path.read_bytes()
        snapshot = json.loads(raw)
        expected_id = ("manly2008-complete" if base_row["article_id"] == "manly2008"
                       and map_path == REPLACEMENTS["manly2008"] else base_row["article_id"])
        require(snapshot["article_id"] == expected_id, "Идентификатор карты изменился")
        require(snapshot["pipeline_id"] == "text_reified" and snapshot["graph_schema_version"] == 6,
                "Требуется карта text_reified схемы 6")
        require(snapshot["source"]["sha256"] != TARGET_SHA256, "Целевая статья обнаружена среди источников")
        validate_map_snapshot(snapshot)
        validation_path = map_path.parent / "validation.json"
        validation = json.loads(validation_path.read_text(encoding="utf-8"))
        require(validation["contract"] == validation["dag"] == validation["provenance"] == "passed",
                "Контракт, DAG или происхождение карты не прошли проверку")
        generation = snapshot.get("generation", {})
        require(generation.get("external_llm_calls", 0) == generation.get("local_llm_calls", 0) == 0,
                "В карте обнаружен вызов модели")
        row = {
            "article_id": snapshot["article_id"],
            "run_id": snapshot["run_id"],
            "path": str(map_path),
            "file_sha256": sha(raw),
            "source_sha256": snapshot["source"]["sha256"],
            "family": base_row["family"],
        }
        sources.append(row)
        if base_row["article_id"] in REPLACEMENTS:
            actions = sum(item["kind"] == "action" for item in snapshot["graph"]["knowledge"])
            replacements.append({**row,
                                 "knowledge_count": len(snapshot["graph"]["knowledge"]),
                                 "action_count": actions,
                                 "transition_count": len(snapshot["graph"]["transitions"]),
                                 "builder_version": snapshot["builder_version"],
                                 "validation": validation})

    require(len(sources) == 16 and len({row["article_id"] for row in sources}) == 16,
            "Состав корпуса должен остаться 16 уникальными статьями")
    manifest = {"version": "joint-motif-explicit-inputs-1",
                "origin_run_id": "cohort-operation-map-revision-1",
                "origin_file_sha256": sha(BASE_MANIFEST.read_bytes()),
                "family_definition": "Publication provenance only; independence not certified",
                "sources": sources}
    return manifest, {"replacements": replacements}


def main() -> None:
    disable_network()
    manifest, audit = build_manifest()
    manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
    write_immutable(OUTPUT / "source-manifest.json", manifest_bytes)
    preparation = {
        "protocol": "source-grounded-cohort-operation-motif-audit-1",
        "base_manifest_sha256": manifest["origin_file_sha256"],
        "expanded_manifest_sha256": sha(manifest_bytes),
        "replacements": audit["replacements"],
        "held_out_target_source_sha256": TARGET_SHA256,
        "target_excluded_by_source_hash": True,
        "network_disabled": True,
        "external_llm_calls": 0,
        "local_llm_calls": 0,
        "expert_validated": False,
    }
    write_immutable(OUTPUT / "preparation.json",
                    json.dumps(preparation, ensure_ascii=False, indent=2).encode("utf-8"))
    result_path = run_audit(OUTPUT / "source-manifest.json", OUTPUT, TARGET_SHA256)
    print(result_path)


if __name__ == "__main__":
    main()

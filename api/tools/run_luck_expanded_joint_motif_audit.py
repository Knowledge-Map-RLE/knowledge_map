"""Пересчитывает аудит совместных мотивов с новой картой Luck 2010."""
from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

from domain.article_maps import require
from infrastructure.immutable_files import write_immutable
from tools.audit_joint_operator_patterns import run as run_audit
from tools.run_free_prediction import disable_network


ROOT = Path(__file__).resolve().parents[2]
OLD_MANIFEST = ROOT / "eval/whole_map_forecast/joint-role-motif-audit-v1/source-manifest.json"
LUCK_MAP = ROOT / "eval/whole_map_forecast/luck2010-complete-map-v1/runs/0249331c-b60f-5e92-84cc-11d62142796e/map.json"
OUTPUT = ROOT / "eval/whole_map_forecast/research-corpus-extension-v1/luck-joint-motif-v2"
TARGET_SHA256 = "f7df96ff746be4a60a6930ff2c5c25435725d0591dfe1f492259624b2d7c0bc8"
LUCK_TEXT_SHA256 = "d5e15ac426b3c43e116dfa0ef038992c8aa104ffcb588b36419fa8685ccb8cd3"


def sha(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def main() -> None:
    disable_network()
    manifest = json.loads(OLD_MANIFEST.read_text(encoding="utf-8"))
    require(manifest["version"] == "joint-motif-explicit-inputs-1", "Ожидался зафиксированный манифест аудита")
    raw_map = LUCK_MAP.read_bytes()
    luck = json.loads(raw_map)
    require(luck["article_id"] == "luck2010" and luck["pipeline_id"] == "text_reified",
            "Ожидалась отдельная карта Luck 2010")
    require(luck["source"]["sha256"] == LUCK_TEXT_SHA256 and luck["graph_schema_version"] == 6,
            "Хеш источника или схема карты Luck 2010 изменились")
    require(luck["needs_expert_review"] is True, "Черновая карта должна быть отмечена на экспертную проверку")
    require(luck["source"]["sha256"] != TARGET_SHA256, "Целевая статья не может входить в обучающий срез")
    luck_rows = [row for row in manifest["sources"] if row["article_id"] == "luck2010"]
    require(len(luck_rows) == 1, "В исходном манифесте должна быть ровно одна карта Luck 2010")
    luck_rows[0].update({
        "run_id": luck["run_id"],
        "path": str(LUCK_MAP),
        "file_sha256": sha(raw_map),
        "source_sha256": luck["source"]["sha256"],
    })
    require(all(row["source_sha256"] != TARGET_SHA256 for row in manifest["sources"]),
            "В обучающий корпус попал источник PMC10000452")
    require(len(manifest["sources"]) == 14, "Ожидался тот же корпус из 14 карт")

    manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
    write_immutable(OUTPUT / "source-manifest.json", manifest_bytes)
    receipt = {
        "protocol": "joint-author-motif-census-with-expanded-luck-map-1",
        "source_manifest_sha256": sha(manifest_bytes),
        "replaced_article_id": "luck2010",
        "replacement_map_run_id": luck["run_id"],
        "replacement_map_sha256": sha(raw_map),
        "replacement_source_sha256": LUCK_TEXT_SHA256,
        "held_out_target_source_sha256": TARGET_SHA256,
        "model_calls": 0,
        "network_disabled": True,
        "expert_validated": False,
    }
    write_immutable(OUTPUT / "preparation.json", json.dumps(receipt, ensure_ascii=False, indent=2).encode("utf-8"))
    result = run_audit(OUTPUT / "source-manifest.json", OUTPUT, TARGET_SHA256)
    print(result)


if __name__ == "__main__":
    main()

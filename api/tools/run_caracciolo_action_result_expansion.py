"""Добавляет проверенную карту Caracciolo к замороженной ретроспективной диагностике."""
from __future__ import annotations

import json
import sys
from hashlib import sha256
from pathlib import Path

ROOT = Path(r"D:\Knowledge_Map")
sys.path.insert(0, str(ROOT / "api"))

from domain.article_maps import require
from infrastructure.immutable_files import write_immutable
from tools.run_action_result_transfer import run
from tools.run_free_prediction import disable_network


BASELINE_MANIFEST = ROOT / (
    "eval/whole_map_forecast/action-result-family-ranking-v1/runs/"
    "a4e07c45a850b5e91d5aafcc19430b2cec2c4efb94508ba3e95d28aba25b63f4/"
    "source-manifest.json"
)
MAP_PATH = ROOT / (
    "eval/whole_map_forecast/caracciolo2008-codex-map-v1/runs/"
    "c4777c1d-a4de-5262-97df-0c3d129d3817/map.json"
)
OUTPUT_ROOT = ROOT / "eval/whole_map_forecast/action-result-family-ranking-v2"
INPUT_PATH = OUTPUT_ROOT / "input/source-manifest.json"


def build_manifest() -> dict:
    """Создаёт новый явный манифест, сохраняя предыдущий корпус без изменений."""
    manifest = json.loads(BASELINE_MANIFEST.read_text(encoding="utf-8"))
    require(len(manifest["sources"]) == 18, "Базовый манифест изменился")
    map_raw = MAP_PATH.read_bytes()
    snapshot = json.loads(map_raw)
    require(snapshot["article_id"] == "caracciolo2008", "Неожиданный исходный документ карты")
    require(snapshot["graph"]["schema_version"] == 6, "Требуется карта схемы 6")
    require(snapshot["generation"]["external_llm_calls"] == 0, "Обнаружен внешний модельный вызов")
    require(snapshot["generation"]["local_llm_calls"] == 0, "Обнаружен локальный модельный вызов")
    require(not any(row["article_id"] == snapshot["article_id"] for row in manifest["sources"]),
            "Caracciolo уже есть в базовом манифесте")
    manifest["metadata"]["corpus_revision"] = (
        "Previous 18-map corpus plus a manually authored partial Caracciolo 2008 map"
    )
    manifest["metadata"]["added_source_audit"] = {
        "article_id": snapshot["article_id"],
        "doi": "10.1212/01.wnl.0000288180.21984.cb",
        "cohort": "Kungsholmen Project, baseline 1987",
        "cohort_independence_verified": False,
        "complete_semantic_coverage": False,
        "prior_source_exposure": True,
        "eligible_as_blind_holdout": False,
        "model_calls": 0,
    }
    manifest["sources"].append({
        "article_id": snapshot["article_id"],
        "map_path": str(MAP_PATH),
        "map_sha256": sha256(map_raw).hexdigest(),
        "run_id": snapshot["run_id"],
        "source_sha256": snapshot["source"]["sha256"],
        "support_family": "publication:caracciolo2008",
    })
    return manifest


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    disable_network()
    manifest = build_manifest()
    manifest_raw = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    write_immutable(INPUT_PATH, manifest_raw)
    result = run(INPUT_PATH, OUTPUT_ROOT)
    result["input_manifest_sha256"] = sha256(manifest_raw).hexdigest()
    print(json.dumps({**result, "network_disabled": True, "model_calls": 0}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

"""Готовит чистые фолды: целевой вход содержит метод, но не результаты и не связи."""
from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

from domain.article_maps import require
from domain.cohort_operation_transfer import OPERATOR_FAMILIES
from infrastructure.immutable_files import write_immutable
from tools.run_free_prediction import disable_network

ROOT = Path(r"D:\Knowledge_Map")
BASE = ROOT / "eval/whole_map_forecast/cohort_operation_prediction/result-usage-lopo-v1"
MANIFEST = BASE / "source-manifest.json"
MINIMUM_SUPPORT = 2


def _json_bytes(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")


def main() -> None:
    disable_network()
    manifest_raw = MANIFEST.read_bytes()
    manifest = json.loads(manifest_raw)
    sources = manifest["sources"]
    targets = [row for row in sources if row["operator_families"]]
    require(len(sources) == 16 and len(targets) == 5, "Не совпал ожидаемый корпус 16/5")
    require(all(set(row["operator_families"]) <= OPERATOR_FAMILIES for row in targets),
            "Есть неизвестный класс целевого метода")
    written = []
    input_dir = BASE / "inputs"
    input_dir.mkdir(parents=True, exist_ok=True)
    for target in targets:
        target_id = target["article_id"]
        training = [row for row in sources if row["article_id"] != target_id]
        require(len(training) == 15 and target_id not in {row["article_id"] for row in training},
                "Ошибка исключения целевой статьи")
        fold_input = {
            "protocol": "sanitized-result-usage-method-input-1",
            "source_manifest_sha256": sha256(manifest_raw).hexdigest(),
            "minimum_publication_support": MINIMUM_SUPPORT,
            "target": {
                "article_id": target_id,
                "run_id": target["run_id"],
                "map_sha256": target["map_sha256"],
                "source_sha256": target["source_sha256"],
                "operation_families": sorted(target["operator_families"]),
            },
            "training_sources": [
                {"article_id": row["article_id"], "map_path": row["map_path"],
                 "map_sha256": row["map_sha256"], "source_sha256": row["source_sha256"]}
                for row in sorted(training, key=lambda row: row["article_id"])
            ],
            "target_outputs_or_edges_included": False,
        }
        input_raw = _json_bytes(fold_input)
        path = input_dir / f"{target_id}.json"
        write_immutable(path, input_raw)
        written.append({"article_id": target_id, "input_sha256": sha256(input_raw).hexdigest(),
                        "training_source_count": len(training)})

    index = {"protocol": "sanitized-result-usage-method-inputs-1",
             "source_manifest_sha256": sha256(manifest_raw).hexdigest(),
             "target_output_fields_included": False, "target_edges_included": False,
             "targets": written}
    write_immutable(input_dir / "index.json", _json_bytes(index))
    print(json.dumps(index, ensure_ascii=False))


if __name__ == "__main__":
    main()

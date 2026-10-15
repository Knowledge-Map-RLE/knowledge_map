"""Готовит безопасные входы LOPO, содержащие только методический контекст цели."""
from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

from domain.article_maps import require
from domain.cohort_operation_transfer import OPERATOR_FAMILIES
from infrastructure.immutable_files import write_immutable
from tools.run_free_prediction import disable_network

ROOT = Path(r"D:\Knowledge_Map")
MANIFEST = ROOT / "eval/whole_map_forecast/research-corpus-extension-v1/cohort-operation-transfer-v7/source-manifest.json"
OUTPUT = ROOT / "eval/whole_map_forecast/cohort_operation_prediction/sealed-lopo-v1/inputs"
MINIMUM_SUPPORT = 2


def _json_bytes(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")


def main() -> None:
    disable_network()
    manifest_raw = MANIFEST.read_bytes()
    manifest = json.loads(manifest_raw)
    rows = manifest["sources"]
    require(len({row["article_id"] for row in rows}) == len(rows), "Повторяющиеся статьи в реестре")
    targets = [row for row in rows if row["operator_families"]]
    require(bool(targets), "В реестре нет статей с типизированными методами")
    require(all(set(row["operator_families"]) <= OPERATOR_FAMILIES for row in targets),
            "Реестр содержит неизвестный тип операции")

    written = []
    for target in targets:
        target_id = target["article_id"]
        training = [row for row in rows if row["article_id"] != target_id]
        require(target_id not in {row["article_id"] for row in training}, "Утечка цели в обучение")
        fold_input = {
            "protocol": "sanitized-method-context-input-1",
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
                for row in sorted(training, key=lambda item: item["article_id"])
            ],
        }
        path = OUTPUT / f"{target_id}.json"
        write_immutable(path, _json_bytes(fold_input))
        written.append({"article_id": target_id, "input_path": str(path),
                        "training_count": len(training),
                        "known_operation_families": fold_input["target"]["operation_families"]})

    index = {"protocol": "sanitized-method-context-inputs-1",
             "source_manifest_sha256": sha256(manifest_raw).hexdigest(),
             "target_output_fields_included": False,
             "target_edges_included": False,
             "targets": written}
    write_immutable(OUTPUT / "index.json", _json_bytes(index))
    print(json.dumps(index, ensure_ascii=False))


if __name__ == "__main__":
    main()

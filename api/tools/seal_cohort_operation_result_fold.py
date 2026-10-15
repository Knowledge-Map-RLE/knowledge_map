"""Запечатывает один usage=result фолд, читая только его очищенный вход."""
from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path

from domain.article_maps import require
from domain.cohort_operation_result_transfer import extract_map
from domain.sealed_operation_result_forecast import VERSION, build_fold_prediction
from infrastructure.immutable_files import write_immutable
from tools.run_free_prediction import disable_network

ROOT = Path(r"D:\Knowledge_Map")
BASE = ROOT / "eval/whole_map_forecast/cohort_operation_prediction/result-usage-lopo-v1"


def _json_bytes(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--article-id", required=True)
    args = parser.parse_args()
    disable_network()
    input_path = BASE / "inputs" / f"{args.article_id}.json"
    input_raw = input_path.read_bytes()
    fold_input = json.loads(input_raw)
    require(fold_input["target"]["article_id"] == args.article_id,
            "Идентификатор целевого фолда не совпадает")
    training_rows = {}
    for entry in fold_input["training_sources"]:
        raw = Path(entry["map_path"]).read_bytes()
        require(sha256(raw).hexdigest() == entry["map_sha256"], "Карта обучения изменилась")
        snapshot = json.loads(raw)
        row = extract_map(snapshot)
        require(row["article_id"] == entry["article_id"], "Идентификатор обучающей карты изменился")
        require(row["source_sha256"] == entry["source_sha256"], "Текст обучающей карты изменился")
        training_rows[row["article_id"]] = row

    prediction = build_fold_prediction(fold_input, training_rows,
                                       fold_input["minimum_publication_support"])
    prediction["input_sha256"] = sha256(input_raw).hexdigest()
    prediction["source_manifest_sha256"] = fold_input["source_manifest_sha256"]
    prediction_raw = _json_bytes(prediction)
    run_id = sha256(prediction_raw).hexdigest()[:32]
    run_root = BASE / "runs" / args.article_id / run_id
    write_immutable(run_root / "sealed-prediction.json", prediction_raw)
    seal = {"protocol": VERSION, "run_id": run_id,
            "prediction_sha256": sha256(prediction_raw).hexdigest(),
            "input_sha256": sha256(input_raw).hexdigest(),
            "target_article_id": args.article_id,
            "target_outputs_or_edges_available_to_forecaster": False,
            "sealed": True}
    write_immutable(run_root / "seal.json", _json_bytes(seal))
    print(json.dumps({"article_id": args.article_id, "run_id": run_id,
                      "sealed_prediction": str(run_root / "sealed-prediction.json"),
                      "training_source_count": len(training_rows),
                      "forecast_counts": {mode: len(rows) for mode, rows in prediction["forecasts"].items()},
                      "network_disabled": True, "model_calls": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()

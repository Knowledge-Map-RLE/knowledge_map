"""Автономный административный сценарий без AI-клиентов, сети и общей Neo4j."""
import argparse
import json
import logging
from pathlib import Path
import socket
from hashlib import sha256

from application.free_prediction import SealFreePrediction, EvaluateFreePrediction
from infrastructure.free_prediction_snapshots import FileForecastMaps
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.article_comparison_controls import FixedComparisonControls
from infrastructure.immutable_files import write_immutable
from domain.article_maps import require


def disable_network():
    def forbidden(*args, **kwargs):
        raise RuntimeError("Network and model calls are prohibited in the free forecast experiment")
    socket.socket.connect = forbidden
    socket.create_connection = forbidden


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["seal", "evaluate"])
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--target")
    parser.add_argument("--run-id")
    args = parser.parse_args()
    disable_network()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    config = json.loads(Path(args.corpus).read_text(encoding="utf-8"))
    config["metadata"]["implementation_sha256"] = {name: sha256((Path(__file__).resolve().parents[1] / name).read_bytes()).hexdigest()
        for name in ("domain/free_prediction.py", "domain/development_prediction.py", "domain/reference_prediction.py",
                     "domain/comparison_normalization.py", "domain/article_comparison.py", "application/free_prediction.py",
                     "infrastructure/free_prediction_snapshots.py", "infrastructure/development_prediction_store.py",
                     "infrastructure/article_comparison_controls.py", "tools/run_free_prediction.py")}
    entries = config["sources"]
    store = FilePredictionStore(args.output)
    owner = "offline-authorized-corpus"
    if args.command == "seal":
        if args.target or args.run_id:
            parser.error("seal accepts sources only")
        maps = FileForecastMaps(entries, owner)
        artifact = SealFreePrediction(maps, store).execute([e["reference"] for e in entries],
            {e["reference"]["article_id"]: e["family"] for e in entries}, owner, config["metadata"])
        receipt = {"stage": "seal", "run_id": artifact["run_id"], "reads": maps.reads,
                   "model_calls": 0, "network_disabled": True}
        write_immutable(store.path(artifact["run_id"]) / "source-read-receipt.json", store.encode(receipt))
        print(json.dumps({"run_id": artifact["run_id"], "counts": {k: len(v) for k,v in artifact["predictions"].items()},
                          "diagnostics": {**artifact["diagnostics"], "witness_screening": artifact["diagnostics"]["witness_screening"]["counts"]}}, ensure_ascii=False))
    else:
        if not args.target or not args.run_id:
            parser.error("evaluate requires a sealed run and an explicit target")
        # В этом процессе целевой снимок становится доступен только после проверки фиксации.
        sealed = store.read_seal(args.run_id)
        require(sealed is not None, "Forecast must be sealed before target loading")
        require(sealed["binding"]["corpus_metadata"]["implementation_sha256"] == config["metadata"]["implementation_sha256"],
                "Frozen implementation changed; evaluation requires its original code")
        target = json.loads(Path(args.target).read_text(encoding="utf-8"))
        maps = FileForecastMaps([*entries, target], owner)
        result = EvaluateFreePrediction(maps, store, FixedComparisonControls()).execute(args.run_id, target["reference"], owner)
        receipt = {"stage": "evaluate", "evaluation_id": result["evaluation_id"], "reads": maps.reads,
                   "model_calls": 0, "network_disabled": True}
        write_immutable(store.path(args.run_id) / (result["evaluation_id"] + ".receipt.json"), store.encode(receipt))
        print(json.dumps({"evaluation_id": result["evaluation_id"], "debugging_success": result["debugging_success"],
                         "modes": {k: {n: v[n] for n in ("candidate_count", "matched_candidate_count", "matched_target_knowledge", "partial_target_knowledge")}
                                   for k,v in result["modes"].items()}}, ensure_ascii=False))


if __name__ == "__main__":
    main()

"""Автономный оценщик: сеть и модельные клиенты не используются."""
import argparse
import json
from hashlib import sha256
from pathlib import Path

from application.transfer_control import AuditTransferControl
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from infrastructure.transfer_control import FileControlInputs
from tools.run_free_prediction import disable_network

CODE = ("domain/transfer_control.py", "domain/qualitative_relations.py", "domain/article_maps.py",
        "application/transfer_control.py", "application/ports/transfer_control.py", "application/ports/development_prediction.py",
        "infrastructure/transfer_control.py", "infrastructure/development_prediction_store.py",
        "infrastructure/immutable_files.py", "tools/audit_transfer_control.py", "tools/run_free_prediction.py")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    disable_network()
    api = Path(__file__).resolve().parents[1]
    code = {name: sha256((api / name).read_bytes()).hexdigest() for name in CODE}
    port = FileControlInputs(args.manifest)
    store = FilePredictionStore(args.output)
    result = AuditTransferControl(port, store).execute(code)
    for name in CODE:
        write_immutable(store.path(result["run_id"]) / "implementation" / name, (api / name).read_bytes())
    write_immutable(store.path(result["run_id"]) / "reads.json", store.encode({
        "reads": port.reads, "network_disabled": True, "model_calls": 0,
        "generation_rerun": False, "forecast_modified": False}))
    print(json.dumps({"run_id": result["run_id"], "modes": {
        mode: {key: value[key] for key in ("candidate_count", "counts", "decisive_candidates", "direction_accuracy")}
        for mode, value in result["audit"]["modes"].items()}, "model_calls": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()

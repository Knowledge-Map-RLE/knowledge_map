"""Автономный CLI вложенного опыта: отдельные команды фиксации и оценки."""
import argparse
import json
import logging
from hashlib import sha256
from pathlib import Path

from application.conditional_cohort_transfer import SealConditionalTransfer, EvaluateConditionalTransfer
from domain.article_maps import require
from infrastructure.cohort_transfer_files import FileCohortTransferInputs
from infrastructure.empirical_inference_files import FileEmpiricalControls
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from tools.run_cohort_transfer import CODE as COHORT_CODE
from tools.run_free_prediction import disable_network

CODE = (*COHORT_CODE, "domain/conditional_cohort_transfer.py", "application/conditional_cohort_transfer.py",
        "infrastructure/immutable_files.py", "tools/run_free_prediction.py", "tools/run_conditional_cohort_transfer.py")


def implementation():
    api = Path(__file__).resolve().parents[1]
    return {name: sha256((api/name).read_bytes()).hexdigest() for name in CODE}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("seal", "evaluate"))
    parser.add_argument("--output", required=True)
    for name in ("manifest", "controls", "run-id"):
        parser.add_argument("--"+name)
    args = parser.parse_args()
    disable_network()
    logging.basicConfig(level=logging.INFO)
    store, code = FilePredictionStore(args.output), implementation()
    if args.command == "seal":
        require(args.manifest and args.controls is None and args.run_id is None, "Seal must not receive controls")
        port = FileCohortTransferInputs(args.manifest)
        result = SealConditionalTransfer(port, store).execute(code)
        write_immutable(store.path(result["run_id"])/"input-read-receipt.json", store.encode(
            {"stage": "seal", "reads": port.reads, "network_disabled": True, "model_calls": 0}))
        api = Path(__file__).resolve().parents[1]
        for name in CODE:
            write_immutable(store.path(result["run_id"])/"implementation"/name, (api/name).read_bytes())
        print(json.dumps({"run_id": result["run_id"], "selections": [{"fold": f["fold_id"], "selected": f["selection"]["selected"]} for f in result["folds"]]}, ensure_ascii=False))
    else:
        require(args.controls and args.run_id and args.manifest is None, "Evaluation requires sealed run and controls only")
        port = FileEmpiricalControls(args.controls)
        result = EvaluateConditionalTransfer(port, store).execute(args.run_id, code)
        write_immutable(store.path(args.run_id)/(result["evaluation_id"]+".receipt.json"), store.encode(
            {"stage": "evaluate", "reads": port.reads, "network_disabled": True, "model_calls": 0}))
        print(json.dumps({"evaluation_id": result["evaluation_id"], "modes": {m: {k: v for k, v in metric.items() if k != "rows"} for m, metric in result["modes"].items()}, "paired": result["paired"]}))


if __name__ == "__main__":
    main()

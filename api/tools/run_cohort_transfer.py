"""CLI строгих и исследовательских гипотез; источник и оценка разведены."""
import argparse
import json
import logging
from hashlib import sha256
from pathlib import Path

from application.cohort_transfer import SealCohortTransfer, EvaluateCohortTransfer
from domain.article_maps import require
from infrastructure.cohort_transfer_files import FileCohortTransferInputs
from infrastructure.empirical_inference_files import FileEmpiricalControls
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from tools.run_free_prediction import disable_network

CODE=("domain/cohort_transfer.py","domain/empirical_inference.py","domain/article_maps.py","application/cohort_transfer.py",
    "application/ports/cohort_transfer.py","infrastructure/cohort_transfer_files.py","infrastructure/empirical_inference_files.py",
    "infrastructure/development_prediction_store.py","infrastructure/free_prediction_snapshots.py","tools/prepare_cohort_transfer.py","tools/run_cohort_transfer.py")


def implementation():
    api=Path(__file__).resolve().parents[1]
    return {name:sha256((api/name).read_bytes()).hexdigest() for name in CODE}


def main():
    p=argparse.ArgumentParser();p.add_argument("command",choices=["seal","evaluate"])
    p.add_argument("--output",required=True);p.add_argument("--manifest");p.add_argument("--controls");p.add_argument("--run-id")
    args=p.parse_args();disable_network();logging.basicConfig(level=logging.INFO)
    store=FilePredictionStore(args.output);code=implementation()
    if args.command=="seal":
        require(args.manifest is not None and args.controls is None and args.run_id is None,"Seal must not read controls")
        port=FileCohortTransferInputs(args.manifest);result=SealCohortTransfer(port,store).execute(code)
        write_immutable(store.path(result["run_id"])/"input-read-receipt.json",store.encode({"stage":"seal","reads":port.reads,"network_disabled":True,"model_calls":0}))
        api=Path(__file__).resolve().parents[1]
        for name in CODE:write_immutable(store.path(result["run_id"])/"implementation"/name,(api/name).read_bytes())
        print(json.dumps({"run_id":result["run_id"],"queries":sum(f["query_count"] for f in result["folds"]),
            "issued":{mode:sum(r["order"] is not None for f in result["folds"] for r in f["predictions"][mode]) for mode in ("strict","exploratory")}}))
    else:
        require(args.manifest is None and args.controls is not None and args.run_id is not None,"Evaluator requires a seal and controls only")
        port=FileEmpiricalControls(args.controls);result=EvaluateCohortTransfer(port,store).execute(args.run_id,code)
        write_immutable(store.path(args.run_id)/(result["evaluation_id"]+".receipt.json"),store.encode({"stage":"evaluate","reads":port.reads,"network_disabled":True,"model_calls":0}))
        print(json.dumps({"evaluation_id":result["evaluation_id"],"modes":{mode:{k:v for k,v in metric.items() if k!="rows"} for mode,metric in result["modes"].items()},"new_scientific_predictions":0}))


if __name__=="__main__":main()

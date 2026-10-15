"""Отдельные процессы фиксации и оценки типизированного источникового опыта."""
import argparse
import json
import logging
from hashlib import sha256
from pathlib import Path

from application.empirical_inference import SealEmpiricalInference, EvaluateEmpiricalInference
from domain.article_maps import require
from infrastructure.empirical_inference_files import FileEmpiricalInputs, FileEmpiricalControls
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from tools.run_free_prediction import disable_network

CODE = ("domain/empirical_inference.py", "application/empirical_inference.py", "application/ports/empirical_inference.py",
        "infrastructure/empirical_inference_files.py", "infrastructure/development_prediction_store.py", "tools/run_empirical_pilot.py",
        "domain/article_maps.py", "infrastructure/free_prediction_snapshots.py", "tools/prepare_empirical_pilot.py")


def implementation():
    api = Path(__file__).resolve().parents[1]
    return {name:sha256((api/name).read_bytes()).hexdigest() for name in CODE}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("command",choices=["seal","evaluate"])
    p.add_argument("--output",required=True);p.add_argument("--inputs");p.add_argument("--controls");p.add_argument("--run-id")
    args=p.parse_args();disable_network();logging.basicConfig(level=logging.INFO)
    store=FilePredictionStore(args.output);code=implementation()
    if args.command=="seal":
        require(args.inputs is not None and args.controls is None and args.run_id is None,"Source seal cannot load controls")
        port=FileEmpiricalInputs(args.inputs)
        result=SealEmpiricalInference(port,store).execute(code)
        run=result["run_id"]
        write_immutable(store.path(run)/"input-read-receipt.json",store.encode({"stage":"seal","reads":port.reads,"network_disabled":True,"model_calls":0}))
        api=Path(__file__).resolve().parents[1]
        for name in CODE:write_immutable(store.path(run)/"implementation"/name,(api/name).read_bytes())
        print(json.dumps({"run_id":run,"cases":len(result["results"]),"abstentions":sum(r["status"]=="abstain" for r in result["results"])},ensure_ascii=False))
    else:
        require(args.controls is not None and args.inputs is None and args.run_id is not None,"Separate evaluator requires controls and a sealed run")
        port=FileEmpiricalControls(args.controls)
        result=EvaluateEmpiricalInference(port,store).execute(args.run_id,code)
        write_immutable(store.path(args.run_id)/(result["evaluation_id"]+".receipt.json"),store.encode({"stage":"evaluate","reads":port.reads,"network_disabled":True,"model_calls":0}))
        print(json.dumps({"evaluation_id":result["evaluation_id"],"operator":{"matched":result["operator"]["matched"],"total":result["operator"]["case_count"]},
            "nominal_baseline_matched":result["nominal_baseline"]["matched"],"new_scientific_predictions":0},ensure_ascii=False))


if __name__=="__main__":main()

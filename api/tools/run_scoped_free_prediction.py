"""Источниковый прогноз и отдельный оценщик без сети и модельных клиентов."""
import argparse
import json
import logging
from pathlib import Path
from hashlib import sha256
from domain.article_maps import require
from application.scoped_free_prediction import SealScopedPrediction, EvaluateScopedPrediction
from infrastructure.free_prediction_snapshots import FileForecastMaps
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.article_comparison_controls import FixedComparisonControls
from infrastructure.immutable_files import write_immutable
from tools.run_free_prediction import disable_network


def main():
    p=argparse.ArgumentParser();p.add_argument("command",choices=["seal","evaluate"])
    for name in ("corpus","output","audit"):p.add_argument("--"+name,required=True)
    p.add_argument("--target");p.add_argument("--run-id");args=p.parse_args()
    disable_network();logging.basicConfig(level=logging.INFO)
    config=json.loads(Path(args.corpus).read_text(encoding="utf-8"));audit=json.loads(Path(args.audit).read_text(encoding="utf-8"))
    require(audit["binding"]["references"]==[e["reference"] for e in config["sources"]],"Audit corpus differs")
    config["metadata"]["audit_sha256"]=sha256(Path(args.audit).read_bytes()).hexdigest()
    code=("domain/scoped_free_prediction.py","domain/free_prediction.py","domain/development_prediction.py","domain/reference_prediction.py",
        "domain/comparison_normalization.py","domain/article_comparison.py","application/scoped_free_prediction.py",
        "infrastructure/free_prediction_snapshots.py","infrastructure/development_prediction_store.py","infrastructure/article_comparison_controls.py",
        "tools/run_scoped_free_prediction.py")
    config["metadata"]["implementation_sha256"]={name:sha256((Path(__file__).resolve().parents[1]/name).read_bytes()).hexdigest() for name in code}
    store=FilePredictionStore(args.output);entries=config["sources"];owner="offline-authorized-corpus"
    if args.command=="seal":
        require(args.target is None and args.run_id is None,"Seal accepts source corpus only")
        maps=FileForecastMaps(entries)
        result=SealScopedPrediction(maps,store).execute([e["reference"] for e in entries],
            {e["reference"]["article_id"]:e["family"] for e in entries},owner,config["metadata"])
        require(result["binding"]["maps"] and [m["map_sha256"] for m in result["binding"]["maps"]]==audit["binding"]["maps_sha256"],"Audit snapshots differ")
        write_immutable(store.path(result["run_id"])/"source-read-receipt.json",store.encode({"stage":"seal","reads":maps.reads,"network_disabled":True,"model_calls":0}))
        print(json.dumps({"run_id":result["run_id"],"eligible":result["eligible_statement_count"],"ledger_count":len(result["evidence_ledger"]),
            "counts":{k:len(v) for k,v in result["predictions"].items()},"analogy":result["diagnostics"]["analogy"]["counts"]},ensure_ascii=False))
    else:
        require(args.target is not None and args.run_id is not None,"Explicit sealed run and target required")
        sealed=store.read_seal(args.run_id)
        require(sealed is not None and sealed["binding"]["corpus_metadata"]==config["metadata"],"Frozen implementation or audit changed")
        target=json.loads(Path(args.target).read_text(encoding="utf-8"));maps=FileForecastMaps([*entries,target])
        result=EvaluateScopedPrediction(maps,store,FixedComparisonControls()).execute(args.run_id,target["reference"],owner)
        write_immutable(store.path(args.run_id)/(result["evaluation_id"]+".receipt.json"),store.encode({"stage":"evaluate","reads":maps.reads,"network_disabled":True,"model_calls":0}))
        print(json.dumps({"evaluation_id":result["evaluation_id"],"debugging_success":result["debugging_success"],"modes":{
            k:{key:v[key] for key in ("candidate_count","matched_candidate_count","fully_covered_target_blocks","partial_target_knowledge")}
            for k,v in result["modes"].items()}},ensure_ascii=False))


if __name__=="__main__":main()

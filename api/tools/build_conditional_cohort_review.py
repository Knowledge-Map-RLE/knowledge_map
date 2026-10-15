"""Проверяет вложенную изоляцию и собирает отчёт из явных источников после оценки."""
import argparse
import json
from hashlib import sha256
from pathlib import Path

from domain.article_maps import fingerprint, digest, require
from infrastructure.cohort_transfer_files import FileCohortTransferInputs
from infrastructure.conditional_cohort_report import markdown, render
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.free_prediction_snapshots import FileForecastMaps
from infrastructure.immutable_files import write_immutable
from tools.run_conditional_cohort_transfer import implementation
from tools.run_free_prediction import disable_network


def main():
    parser=argparse.ArgumentParser()
    for name in ("prepared","corpus","output","run-id","evaluation-id"):
        parser.add_argument("--"+name,required=True)
    args=parser.parse_args();disable_network()
    prepared=Path(args.prepared).resolve();store=FilePredictionStore(args.output);folder=store.path(args.run_id)
    sealed=store.read_seal(args.run_id)
    require(sealed is not None and sealed["binding"]["implementation"]==implementation(),"Frozen conditional implementation differs")
    evaluation=json.loads((folder/"evaluations"/(args.evaluation_id+".json")).read_text(encoding="utf-8"))
    require(evaluation["evaluation_id"]==args.evaluation_id==fingerprint(evaluation["binding"]),"Evaluation identity differs")
    require(evaluation["binding"]["sealed_sha256"]==fingerprint(sealed),"Evaluation seal differs")
    port=FileCohortTransferInputs(prepared/"inputs-manifest.json");inputs=port.read_inputs()
    manifest,folds=inputs["manifest"],inputs["folds"]
    require(fingerprint(manifest)==sealed["binding"]["manifest_sha256"] and
            [fingerprint(f) for f in folds]==sealed["binding"]["folds_sha256"],"Frozen inputs differ")
    controls=json.loads((prepared/"hidden-controls.json").read_text(encoding="utf-8"))
    require(fingerprint(controls)==evaluation["binding"]["controls_sha256"] and controls["manifest_sha256"]==fingerprint(manifest),"Controls differ")
    corpus=json.loads(Path(args.corpus).read_text(encoding="utf-8"))
    bindings=[{k:e[k] for k in ("reference","pmcid","file_sha256","source_sha256","graph_sha256")} for e in corpus["sources"]]
    require(bindings==manifest["source_bindings"]==sealed["binding"]["source_bindings"],"Explicit source corpus differs")
    maps=FileForecastMaps(corpus["sources"]);sources={}
    for entry in corpus["sources"]:
        ref=entry["reference"];m=maps.get(ref["article_id"],ref["pipeline_id"],maps.owner,ref["run_id"])
        sources[m["article_id"]]={"pmcid":entry["pmcid"],"text":m["source"]["text"],"sha256":m["source"]["sha256"]}
    require(all(s["pmcid"]!="pmc10000452" for s in sources.values()),"Target access prohibited")
    evidence=dict(controls["evidence"])
    for f in folds:
        sf=next(x for x in sealed["folds"] if x["fold_id"]==f["fold_id"])
        require(sorted(o["id"] for o in f["training"])==sf["selection"]["training_observation_ids"],"Fitted observations differ")
        require(f["withheld_family"] not in sf["selection"]["training_families"],"Outer group leaked into fit")
        byid={o["id"]:o["context"]["family_id"] for o in f["training"]}
        for audit in sf["selection"]["inner_audit"]:
            for g in audit["groups"]:
                require(g["validation_family"] not in g["fit_families"],"Inner group leaked into training")
                require(all(byid[k]!=g["validation_family"] for k in g["fit_observation_ids"]),"Inner observation leakage")
                require(all(byid[k]!=g["validation_family"] for r in g["rows"] for k in r["support_observation_ids"]),"Inner witness leakage")
        held_ids={key for c in controls["controls"].values() if c["family_id"]==f["withheld_family"] for key in c["evidence_ids"] if key!="T2:incidence-unit"}
        require(not held_ids & set(f["evidence"]),"Outer numeric evidence leaked")
        for key,proof in f["evidence"].items():
            require(key not in evidence or evidence[key]==proof,"Conflicting source proof")
            evidence[key]=proof
    for proof in evidence.values():
        source=sources[proof["article_id"]]
        require(source["sha256"]==proof["source_sha256"] and source["text"][proof["start"]:proof["end"]]==proof["text"] and digest(proof["text"])==proof["text_sha256"],"Source proof differs")
    receipts={"seal":json.loads((folder/"input-read-receipt.json").read_text(encoding="utf-8")),
              "evaluate":json.loads((folder/(args.evaluation_id+".receipt.json")).read_text(encoding="utf-8"))}
    require(receipts["seal"]["reads"]==port.reads and receipts["evaluate"]["reads"]==[str(prepared/"hidden-controls.json")],"Unexpected stage reads")
    data={"sealed":sealed,"evaluation":evaluation,"manifest":manifest,"folds":folds,"controls":controls,
          "sources":sources,"evidence":evidence,"receipts":receipts,
          "preparation":json.loads((prepared/"preparation-receipt.json").read_text(encoding="utf-8"))}
    files={"report.html":render(data).encode("utf-8"),"report.ru.md":markdown(data).encode("utf-8"),"review.json":store.encode(data),
           "predictions.json":store.encode(sealed),"evaluation.json":store.encode(evaluation),"inputs-manifest.json":store.encode(manifest)}
    review=folder/"review-v1"
    for name,raw in files.items():write_immutable(review/name,raw)
    api=Path(__file__).resolve().parents[1];code=("tools/build_conditional_cohort_review.py","infrastructure/conditional_cohort_report.py")
    proof={"run_id":args.run_id,"evaluation_id":args.evaluation_id,"model_calls":0,"new_scientific_predictions":0,
           "files":{name:sha256(raw).hexdigest() for name,raw in files.items()},"source_bindings":bindings,
           "review_implementation":{name:sha256((api/name).read_bytes()).hexdigest() for name in code}}
    write_immutable(review/"manifest.json",store.encode(proof))
    for name in code:write_immutable(folder/"review-implementation"/name,(api/name).read_bytes())
    print(json.dumps({"report":str(review/"report.html"),"source_fragments":len(evidence),"inner_audits":sum(len(f["selection"]["inner_audit"]) for f in sealed["folds"])},ensure_ascii=False))


if __name__=="__main__":main()

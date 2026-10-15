"""Собирает источниковый отчёт, проверяя числовые и контрольные фрагменты."""
import argparse
import json
from hashlib import sha256
from pathlib import Path

from domain.article_maps import fingerprint, require
from infrastructure.free_prediction_snapshots import FileForecastMaps
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from infrastructure.empirical_inference_report import markdown, render
from tools.run_free_prediction import disable_network
from tools.run_empirical_pilot import implementation


def main():
    p=argparse.ArgumentParser()
    for key in ("prepared","corpus","output","run-id","evaluation-id"):p.add_argument("--"+key,required=True)
    args=p.parse_args();disable_network();prepared=Path(args.prepared)
    store=FilePredictionStore(args.output);folder=store.path(args.run_id);sealed=store.read_seal(args.run_id)
    require(sealed is not None,"Empirical seal required")
    require(sealed["binding"]["implementation"]==implementation(),"Frozen implementation differs")
    evaluation=json.loads((folder/"evaluations"/(args.evaluation_id+".json")).read_text(encoding="utf-8"))
    require(evaluation["binding"]["seal_sha256"]==fingerprint(sealed),"Review seal changed")
    inputs=json.loads((prepared/"inputs.json").read_text(encoding="utf-8"))
    controls=json.loads((prepared/"hidden-controls.json").read_text(encoding="utf-8"))
    preparation=json.loads((prepared/"preparation-receipt.json").read_text(encoding="utf-8"))
    require(fingerprint(inputs)==sealed["binding"]["input_sha256"]==controls["input_sha256"],"Input hash differs")
    require(fingerprint(controls)==evaluation["binding"]["controls_sha256"],"Controls hash differs")
    corpus=json.loads(Path(args.corpus).read_text(encoding="utf-8"))
    bindings=[{k:entry[k] for k in ("reference","pmcid","file_sha256","source_sha256","graph_sha256")} for entry in corpus["sources"]]
    require(bindings==inputs["source_bindings"]==sealed["binding"]["source_bindings"],"Explicit source corpus differs")
    port=FileForecastMaps(corpus["sources"]);sources={}
    for entry in corpus["sources"]:
        ref=entry["reference"];m=port.get(ref["article_id"],ref["pipeline_id"],port.owner,ref["run_id"])
        sources[m["article_id"]]={"pmcid":entry["pmcid"],"text":m["source"]["text"],"sha256":m["source"]["sha256"]}
    evidence={**inputs["evidence"],**controls["evidence"]}
    for proof in evidence.values():
        source=sources[proof["article_id"]]
        require(source["sha256"]==proof["source_sha256"] and source["text"][proof["start"]:proof["end"]]==proof["text"],"Evidence differs from original source")
    receipts={"seal":json.loads((folder/"input-read-receipt.json").read_text(encoding="utf-8")),
        "evaluate":json.loads((folder/(args.evaluation_id+".receipt.json")).read_text(encoding="utf-8"))}
    require(receipts["seal"]["reads"]==[str((prepared/"inputs.json").resolve())] and
            receipts["evaluate"]["reads"]==[str((prepared/"hidden-controls.json").resolve())],"Stages read unexpected files")
    data={"sealed":sealed,"evaluation":evaluation,"inputs":inputs,"controls":controls,"preparation":preparation,
        "receipts":receipts,"sources":sources,"evidence":evidence}
    files={"report.html":render(data).encode("utf-8"),"report.ru.md":markdown(data).encode("utf-8"),
        "inputs.json":store.encode(inputs),"hidden-controls.json":store.encode(controls),"predictions.json":store.encode(sealed),
        "evaluation.json":store.encode(evaluation),"review.json":store.encode(data)}
    review=folder/"review-v1"
    for name,raw in files.items():write_immutable(review/name,raw)
    manifest={"run_id":args.run_id,"evaluation_id":args.evaluation_id,"model_calls":0,"new_scientific_predictions":0,
        "files":{name:sha256(raw).hexdigest() for name,raw in files.items()},"source_bindings":bindings,
        "review_implementation":{name:sha256((Path(__file__).resolve().parents[1]/name).read_bytes()).hexdigest()
            for name in ("tools/build_empirical_review.py","infrastructure/empirical_inference_report.py")}}
    write_immutable(review/"manifest.json",store.encode(manifest))
    for name in manifest["review_implementation"]:write_immutable(folder/"review-implementation"/name,(Path(__file__).resolve().parents[1]/name).read_bytes())
    print(json.dumps({"report":str((review/"report.html").resolve()),"source_articles":len(sources),"evidence_fragments":len(evidence)},ensure_ascii=False))


if __name__=="__main__":main()

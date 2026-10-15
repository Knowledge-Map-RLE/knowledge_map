"""Собирает проверяемый офлайн-отчёт после неизменяемой оценки."""
import argparse
import json
from pathlib import Path
from hashlib import sha256

from domain.article_maps import require, fingerprint
from domain.comparison_normalization import normalize_map
from infrastructure.free_prediction_snapshots import FileForecastMaps
from infrastructure.free_prediction_report import markdown, render
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable


def main():
    p=argparse.ArgumentParser()
    for name in ("corpus","target","output","run-id","evaluation-id"):
        p.add_argument("--"+name,required=True)
    args=p.parse_args()
    store=FilePredictionStore(args.output);folder=store.path(args.run_id)
    sealed=store.read_seal(args.run_id)
    evaluation=json.loads((folder/"evaluations"/(args.evaluation_id+".json")).read_text(encoding="utf-8"))
    require(evaluation["binding"]["prediction_sha256"]==fingerprint(sealed),"Review seal mismatch")
    corpus=json.loads(Path(args.corpus).read_text(encoding="utf-8"));target=json.loads(Path(args.target).read_text(encoding="utf-8"))
    require([e["reference"] for e in corpus["sources"]] == sealed["binding"]["sources"], "Review source versions changed")
    require(target["reference"] == evaluation["binding"]["target"], "Review target version changed")
    entries=[*corpus["sources"],target];maps=FileForecastMaps(entries);sources={}
    for index,entry in enumerate(entries):
        ref=entry["reference"];m=maps.get(ref["article_id"],ref["pipeline_id"],maps.owner,ref["run_id"])
        bound_sha = (sealed["binding"]["maps"][index]["map_sha256"] if index < len(corpus["sources"])
                     else evaluation["binding"]["target_map_sha256"])
        require(fingerprint(m) == bound_sha, "Review snapshot differs from evaluated map")
        ru=json.loads((Path(entry["path"]).parent/"translation.ru.json").read_text(encoding="utf-8"))
        statements={}
        for k in normalize_map(m):
            for s in k["statements"]:
                statements[s["id"]]={"knowledge_id":k["id"],"text":k["text"],"text_ru":ru[k["id"]],"provenance":s["provenance"]}
        sources[m["article_id"]]={"pmcid":entry["pmcid"],"title":entry["title"],"text":m["source"]["text"],
                                 "sha256":m["source"]["sha256"],"units":m["source"]["units"],"statements":statements}
    receipts={"seal":json.loads((folder/"source-read-receipt.json").read_text(encoding="utf-8")),
              "evaluate":json.loads((folder/(args.evaluation_id+".receipt.json")).read_text(encoding="utf-8"))}
    require(len(receipts["seal"]["reads"])==len(corpus["sources"]) and len(receipts["evaluate"]["reads"])==1,"Unexpected corpus reads")
    data={"sealed":sealed,"evaluation":evaluation,"sources":sources,"target_article_id":target["reference"]["article_id"],
          "receipts":receipts,"seal_proof":json.loads((folder/"seal.json").read_text(encoding="utf-8"))}
    files={"report.html":render(data).encode("utf-8"),"report.ru.md":markdown(sealed,evaluation,corpus["sources"]).encode("utf-8"),
           "predictions.json":store.encode(sealed),"evaluation.json":store.encode(evaluation),
           "review.json":store.encode(data)}
    review=folder/"review-v1"
    for name,raw in files.items():write_immutable(review/name,raw)
    manifest={"run_id":args.run_id,"evaluation_id":args.evaluation_id,"expert_validated":False,"model_calls":0,
              "files":{name:sha256(raw).hexdigest() for name,raw in files.items()},"source_snapshots":[{k:e[k] for k in ("pmcid","file_sha256","source_sha256","graph_sha256")} for e in entries]}
    write_immutable(review/"manifest.json",store.encode(manifest))
    print(json.dumps({"report":str((review/"report.html").resolve()),"files":len(files)},ensure_ascii=False))


if __name__=="__main__":main()

"""Собирает отчёт только из проверенных зафиксированных результатов."""
import argparse
import json
from collections import Counter
from hashlib import sha256
from pathlib import Path

from domain.article_maps import require, fingerprint
from domain.comparison_normalization import normalize_map
from infrastructure.free_prediction_snapshots import FileForecastMaps
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.immutable_files import write_immutable
from infrastructure.scoped_free_prediction_report import markdown, render
from tools.run_free_prediction import disable_network


def main():
    p=argparse.ArgumentParser()
    for name in ("corpus","target","output","run-id","evaluation-id","audit","preliminary-run"):
        p.add_argument("--"+name,required=True)
    args=p.parse_args();disable_network()
    store=FilePredictionStore(args.output);folder=store.path(args.run_id)
    sealed=store.read_seal(args.run_id);preliminary=store.read_seal(args.preliminary_run)
    require(sealed is not None and preliminary is not None,"Both seals required")
    evaluation=json.loads((folder/"evaluations"/(args.evaluation_id+".json")).read_text(encoding="utf-8"))
    require(evaluation["binding"]["prediction_sha256"]==fingerprint(sealed),"Review seal mismatch")
    audit=json.loads(Path(args.audit).read_text(encoding="utf-8"))
    require(sha256(Path(args.audit).read_bytes()).hexdigest()==sealed["binding"]["corpus_metadata"]["audit_sha256"],"Audit differs")
    corpus=json.loads(Path(args.corpus).read_text(encoding="utf-8"));target=json.loads(Path(args.target).read_text(encoding="utf-8"))
    refs=[e["reference"] for e in corpus["sources"]]
    require(refs==sealed["binding"]["sources"]==preliminary["binding"]["sources"]==audit["binding"]["references"],"Source versions differ")
    require(sealed["binding"]["maps"]==preliminary["binding"]["maps"],"Preliminary snapshots differ")
    require(target["reference"]==evaluation["binding"]["target"],"Target version differs")
    entries=[*corpus["sources"],target];maps=FileForecastMaps(entries);sources={}
    for index,entry in enumerate(entries):
        ref=entry["reference"];m=maps.get(ref["article_id"],ref["pipeline_id"],maps.owner,ref["run_id"])
        bound=sealed["binding"]["maps"][index]["map_sha256"] if index<len(refs) else evaluation["binding"]["target_map_sha256"]
        require(fingerprint(m)==bound,"Review snapshot differs from sealed/evaluated map")
        ru=json.loads((Path(entry["path"]).parent/"translation.ru.json").read_text(encoding="utf-8"))
        statements={s["id"]:{"knowledge_id":k["id"],"text":k["text"],"text_ru":ru[k["id"]],"provenance":s["provenance"]}
                    for k in normalize_map(m) for s in k["statements"]}
        sources[m["article_id"]]={"pmcid":entry["pmcid"],"title":entry["title"],"text":m["source"]["text"],
            "sha256":m["source"]["sha256"],"units":m["source"]["units"],"statements":statements}
    receipts={"seal":json.loads((folder/"source-read-receipt.json").read_text(encoding="utf-8")),
        "evaluate":json.loads((folder/(args.evaluation_id+".receipt.json")).read_text(encoding="utf-8"))}
    target_id=target["reference"]["article_id"]
    require(len(receipts["seal"]["reads"])==len(refs) and all(x["article_id"]!=target_id for x in receipts["seal"]["reads"]),"Target in seal receipts")
    require([x["article_id"] for x in receipts["evaluate"]["reads"]]==[target_id],"Unexpected evaluator reads")
    # Пробный источниковый вариант не оценивался; отчёт не превращает его в прогноз.
    require(not (store.path(args.preliminary_run)/"evaluations").exists(),"Preliminary run already evaluated")
    data={"sealed":sealed,"evaluation":evaluation,"preliminary":preliminary,"audit":audit,"sources":sources,
        "target_article_id":target_id,"receipts":receipts,"seal_proof":json.loads((folder/"seal.json").read_text(encoding="utf-8"))}
    files={"report.html":render(data).encode("utf-8"),"report.ru.md":markdown(data).encode("utf-8"),
        "predictions.json":store.encode(sealed),"evaluation.json":store.encode(evaluation),"audit.json":store.encode(audit),
        "preliminary-rejected.json":store.encode(preliminary),"review.json":store.encode(data)}
    review=folder/"review-v1"
    for name,raw in files.items():write_immutable(review/name,raw)
    manifest={"run_id":args.run_id,"evaluation_id":args.evaluation_id,"expert_validated":False,"model_calls":0,
        "files":{name:sha256(raw).hexdigest() for name,raw in files.items()},
        "source_snapshots":[{k:e[k] for k in ("pmcid","file_sha256","source_sha256","graph_sha256")} for e in entries]}
    write_immutable(review/"manifest.json",store.encode(manifest))
    print(json.dumps({"report":str((review/"report.html").resolve()),"files":len(files),"ledger":dict(Counter(x["kind"] for x in sealed["evidence_ledger"]))},ensure_ascii=False))


if __name__=="__main__":main()

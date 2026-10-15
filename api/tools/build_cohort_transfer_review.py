"""Собирает автономный отчёт после проверки фиксации и точных источников."""
import argparse
import json
from hashlib import sha256
from pathlib import Path

from domain.article_maps import fingerprint, digest, require
from infrastructure.cohort_transfer_files import FileCohortTransferInputs
from infrastructure.cohort_transfer_report import markdown, render, paired_comparison
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.free_prediction_snapshots import FileForecastMaps
from infrastructure.immutable_files import write_immutable
from tools.run_cohort_transfer import implementation
from tools.run_free_prediction import disable_network


def main():
    parser = argparse.ArgumentParser()
    for name in ("prepared", "corpus", "output", "run-id", "evaluation-id"):
        parser.add_argument("--"+name, required=True)
    args = parser.parse_args()
    disable_network()
    prepared = Path(args.prepared).resolve()
    store = FilePredictionStore(args.output)
    folder = store.path(args.run_id)
    sealed = store.read_seal(args.run_id)
    require(sealed is not None, "Seal required")
    require(sealed["binding"]["implementation"] == implementation(), "Frozen code differs")
    evaluation = json.loads((folder/"evaluations"/(args.evaluation_id+".json")).read_text(encoding="utf-8"))
    require(evaluation["binding"]["sealed_sha256"] == fingerprint(sealed), "Evaluation seal differs")
    require(evaluation["evaluation_id"] == args.evaluation_id == fingerprint(evaluation["binding"]), "Evaluation identity differs")
    port = FileCohortTransferInputs(prepared/"inputs-manifest.json")
    inputs = port.read_inputs()
    manifest, folds = inputs["manifest"], inputs["folds"]
    require(fingerprint(manifest) == sealed["binding"]["manifest_sha256"], "Manifest changed")
    require([fingerprint(f) for f in folds] == sealed["binding"]["folds_sha256"], "Folds changed")
    controls = json.loads((prepared/"hidden-controls.json").read_text(encoding="utf-8"))
    require(fingerprint(controls) == evaluation["binding"]["controls_sha256"], "Controls changed")
    require(controls["manifest_sha256"] == fingerprint(manifest), "Controls belong to another manifest")
    corpus = json.loads(Path(args.corpus).read_text(encoding="utf-8"))
    bindings = [{k: entry[k] for k in ("reference", "pmcid", "file_sha256", "source_sha256", "graph_sha256")} for entry in corpus["sources"]]
    require(bindings == manifest["source_bindings"] == sealed["binding"]["source_bindings"], "Explicit corpus differs")
    maps = FileForecastMaps(corpus["sources"])
    sources = {}
    for entry in corpus["sources"]:
        ref = entry["reference"]
        m = maps.get(ref["article_id"], ref["pipeline_id"], maps.owner, ref["run_id"])
        sources[m["article_id"]] = {"pmcid": entry["pmcid"], "text": m["source"]["text"], "sha256": m["source"]["sha256"]}
    require(all(s["pmcid"] != "pmc10000452" for s in sources.values()), "Target access prohibited")
    evidence = dict(controls["evidence"])
    for fold in folds:
        for key, proof in fold["evidence"].items():
            require(key not in evidence or evidence[key] == proof, "Conflicting evidence")
            evidence[key] = proof
        held_ids = {key for c in controls["controls"].values() if c["family_id"] == fold["withheld_family"]
                    for key in c["evidence_ids"] if key != "T2:incidence-unit"}
        require(not held_ids & set(fold["evidence"]), "Held-out numeric evidence leaked")
    for proof in evidence.values():
        source = sources[proof["article_id"]]
        require(source["sha256"] == proof["source_sha256"] and source["text"][proof["start"]:proof["end"]] == proof["text"], "Source excerpt differs")
        require(digest(proof["text"]) == proof["text_sha256"], "Excerpt hash differs")
    receipts = {"seal": json.loads((folder/"input-read-receipt.json").read_text(encoding="utf-8")),
                "evaluate": json.loads((folder/(args.evaluation_id+".receipt.json")).read_text(encoding="utf-8"))}
    require(receipts["seal"]["reads"] == port.reads and receipts["evaluate"]["reads"] == [str(prepared/"hidden-controls.json")], "Unexpected stage reads")
    data = {"sealed": sealed, "evaluation": evaluation, "manifest": manifest, "folds": folds, "controls": controls,
            "preparation": json.loads((prepared/"preparation-receipt.json").read_text(encoding="utf-8")),
            "sources": sources, "evidence": evidence, "receipts": receipts, "paired": paired_comparison(evaluation)}
    files = {"report.html": render(data).encode("utf-8"), "report.ru.md": markdown(data).encode("utf-8"),
             "review.json": store.encode(data), "predictions.json": store.encode(sealed), "evaluation.json": store.encode(evaluation),
             "inputs-manifest.json": store.encode(manifest), "hidden-controls.json": store.encode(controls)}
    review = folder/"review-v1"
    for name, raw in files.items():
        write_immutable(review/name, raw)
    api = Path(__file__).resolve().parents[1]
    code = ("tools/build_cohort_transfer_review.py", "infrastructure/cohort_transfer_report.py")
    review_manifest = {"run_id": args.run_id, "evaluation_id": args.evaluation_id, "model_calls": 0, "new_scientific_predictions": 0,
                      "files": {name: sha256(raw).hexdigest() for name, raw in files.items()}, "source_bindings": bindings,
                      "review_implementation": {name: sha256((api/name).read_bytes()).hexdigest() for name in code}}
    write_immutable(review/"manifest.json", store.encode(review_manifest))
    for name in code:
        write_immutable(folder/"review-implementation"/name, (api/name).read_bytes())
    print(json.dumps({"report": str(review/"report.html"), "evidence_fragments": len(evidence), "paired": data["paired"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

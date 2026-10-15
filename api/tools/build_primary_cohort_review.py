"""Публикация неизменяемого отчёта из явно заданных первичных источников."""
import argparse
import json
from hashlib import sha256
from pathlib import Path

from application.primary_qualification import validate_primary_qualification
from domain.article_maps import fingerprint, require
from infrastructure.primary_cohort_sources import FilePrimarySourceStore
from infrastructure.primary_cohort_review import build_primary_html, build_primary_markdown
from infrastructure.immutable_files import write_immutable
from infrastructure.development_prediction_store import FilePredictionStore


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", required=True)
    parser.add_argument("--annotation", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root, annotation_path, out = Path(args.audit).resolve(), Path(args.annotation).resolve(), Path(args.output).resolve()
    audit = json.loads((root / "audit.json").read_text(encoding="utf-8"))
    registry = json.loads((root / "registry.json").read_text(encoding="utf-8"))
    require(fingerprint(registry) == audit["registry_sha256"], "Registry changed")
    annotation = json.loads(annotation_path.read_text(encoding="utf-8"))
    require(annotation["audit_sha256"] == fingerprint(audit), "Annotation belongs to another audit")
    controls = json.loads((root / "control-metadata.json").read_text(encoding="utf-8"))
    require(fingerprint(controls) == audit["control_metadata_sha256"], "Control metadata changed")
    require(controls["abstracts_read"] is False and controls["fulltexts_read"] is False, "Control content exposure differs")
    store = FilePrimarySourceStore(root / "sources")
    records = []
    texts = {}
    for record in audit["additional_sources"]:
        checked = store.read(record["entry"])
        require(checked == record and checked["status"] == "training_fulltext_saved", "Audited source differs")
        records.append(checked)
        texts[checked["entry"]["id"]] = (root / "sources" / checked["entry"]["id"] / "article.md").read_text(encoding="utf-8")
    validation = validate_primary_qualification(annotation, records, texts)
    data = {"audit": audit, "annotation": annotation, "source_texts": texts, "controls": controls, "validation": validation}
    files = {"report.html": build_primary_html(data).encode("utf-8"), "report.md": build_primary_markdown(data).encode("utf-8"),
             "data.json": FilePredictionStore.encode(data), "validation.json": FilePredictionStore.encode(validation)}
    api = Path(__file__).resolve().parents[1]
    names = ("domain/primary_evidence.py", "application/primary_qualification.py", "infrastructure/primary_cohort_review.py", "tools/build_primary_cohort_review.py")
    code = {name: (api / name).read_bytes() for name in names}
    require(all(sha256((api / name).read_bytes()).hexdigest() == value for name, value in audit["implementation"].items()), "Source audit implementation changed")
    manifest = {"version": "primary-cohort-review-1", "audit_sha256": fingerprint(audit), "annotation_sha256": fingerprint(annotation),
                "files": {name: sha256(value).hexdigest() for name, value in files.items()},
                "implementation": {name: sha256(value).hexdigest() for name, value in code.items()},
                "annotation_preparer_sha256": sha256((root / "prepare_qualification.py").read_bytes()).hexdigest(),
                "model_calls": 0, "new_scientific_predictions": 0, "expert_validated": False}
    for name, raw in files.items():
        write_immutable(out / name, raw)
    for name, raw in code.items():
        write_immutable(out / "implementation" / name, raw)
    write_immutable(out / "annotation-preparer.py", (root / "prepare_qualification.py").read_bytes())
    write_immutable(out / "annotation.json", FilePredictionStore.encode(annotation))
    write_immutable(out / "manifest.json", FilePredictionStore.encode(manifest))
    print(json.dumps({"report": str(out / "report.html"), "validation": validation}, ensure_ascii=False))


if __name__ == "__main__":
    main()

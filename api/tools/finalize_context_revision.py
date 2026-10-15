"""Административная публикация диагностики контекста на фиксированных запусках."""
import argparse
import ctypes
import json
import sys
from pathlib import Path

API = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API))

from domain.article_maps import require, fingerprint
from infrastructure.context_revision_report import save_context_review
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.prepared_research_maps import PreparedResearchMaps
from tools.import_codex_article_map import prohibit_generation
from tools.run_prepared_question_pilot import read, bundles_from_manifest


def main():
    parser = argparse.ArgumentParser(description="Обзор подтверждённых уточнений и отдельной sensitivity-ветки")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--previous-root", type=Path, required=True)
    parser.add_argument("--previous-run-id", required=True)
    parser.add_argument("--review-version", type=int, default=1)
    args = parser.parse_args()
    require(sys.platform == "win32" and bool(ctypes.windll.shell32.IsUserAnAdmin()), "Administrative CLI required")
    prohibit_generation()
    require(args.review_version >= 1, "Positive report revision required")
    previous = FilePredictionStore(args.previous_root).read_seal(args.previous_run_id)
    forecasts, prepared = {}, {}
    for scope in ("primary", "sensitivity"):
        root = args.root / scope
        receipt = read(root / "diagnostic-v1" / "receipt-v1.json")
        forecast = FilePredictionStore(root / "diagnostic-v1" / "runs").read_seal(receipt["run_id"])
        manifest = read(root / "manifest-v1.json")
        bundles = bundles_from_manifest(manifest, root)
        maps = PreparedResearchMaps(bundles, manifest["owner"], "training")
        require(previous and forecast and forecast["binding"]["owner"] == manifest["owner"] == previous["binding"]["owner"], "Context report owner differs")
        for b in bundles:
            m = b["map"]
            maps.get(m["article_id"], m["pipeline_id"], manifest["owner"], m["run_id"])
        require(forecast["binding"]["maps"] == [{"article_id": b["map"]["article_id"], "graph_sha256": fingerprint(b["map"]["graph"]), "source_sha256": b["map"]["source"]["sha256"]} for b in bundles], "Context report map binding differs")
        require(forecast["binding"]["annotations_sha256"] == fingerprint({b["map"]["article_id"]: b["annotation"] for b in bundles}), "Context report annotation binding differs")
        forecasts[scope], prepared[scope] = forecast, bundles
    table = next(t for b in prepared["primary"] if b["origin"].get("context_revision") for t in b["origin"]["context_revision"]["audit"]["tables"])
    folder = args.root / f"review-v{args.review_version}"
    save_context_review(folder, previous, forecasts, prepared, table)
    print(json.dumps({"folder": folder.as_posix(), "runs": {scope: f["run_id"] for scope, f in forecasts.items()}, "model_calls": 0, "future_target_read": False}))


if __name__ == "__main__":
    main()

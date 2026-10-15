"""Административный опыт на явно заданных источниках; модельные вызовы запрещены."""
import argparse
import ctypes
import json
import logging
import sys
from pathlib import Path

API = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API))
from application.qualitative_question_prediction import SealQualitativeQuestionExperiment
from application.question_prediction import AuditResearchSemantics
from domain.article_maps import fingerprint, require
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.prepared_research_maps import PreparedResearchMaps
from infrastructure.research_artifacts import FileResearchArtifacts
from infrastructure.qualitative_question_report import save_qualitative_review
from infrastructure.immutable_files import write_immutable
from tools.run_prepared_question_pilot import read, bundles_from_manifest
from tools.import_codex_article_map import prohibit_generation


def main():
    parser = argparse.ArgumentParser(description="Качественный прогноз без моделей на фиксированном корпусе")
    for name in ("manifest", "policy", "output", "previous_root", "table_media"):
        parser.add_argument("--" + name.replace("_", "-"), required=True, type=Path)
    parser.add_argument("--previous-run-id", required=True)
    parser.add_argument("--analysis-scope", choices=("primary", "sensitivity"), default="primary")
    args = parser.parse_args()
    require(sys.platform == "win32" and bool(ctypes.windll.shell32.IsUserAnAdmin()), "Administrative CLI required")
    prohibit_generation()
    logging.basicConfig(level=logging.INFO)
    manifest = read(args.manifest)
    policy = read(args.policy)
    bundles = bundles_from_manifest(manifest, args.manifest.parent)
    maps = PreparedResearchMaps(bundles, manifest["owner"], "training")
    refs = [{k: b["map"][k] for k in ("article_id", "pipeline_id", "run_id")} for b in bundles]
    registry = {b["map"]["article_id"]: b["registry"] for b in bundles}
    annotations = {b["map"]["article_id"]: b["annotation"] for b in bundles}
    previous = FilePredictionStore(args.previous_root).read_seal(args.previous_run_id)
    require(previous and previous["binding"]["sources"] == refs, "Use the unchanged previous corpus")
    require(previous["binding"]["owner"] == manifest["owner"], "Previous forecast belongs to another owner")
    expected = [{"article_id": b["map"]["article_id"], "graph_sha256": fingerprint(b["map"]["graph"]), "source_sha256": b["map"]["source"]["sha256"]} for b in bundles]
    prior = previous["binding"]["maps"]
    require(all(set(m) in ({"graph_sha256", "source_sha256"}, {"article_id", "graph_sha256", "source_sha256"}) for m in prior), "Unknown previous map binding")
    require(len(prior) == len(expected) and all(m == ({k: v for k, v in e.items() if k != "article_id"} if "article_id" not in m else e)
                                             for m, e in zip(prior, expected)), "Previous source or graph changed")
    write_immutable(args.output / "policy.snapshot.json", args.policy.read_bytes())
    audit = AuditResearchSemantics(maps, FileResearchArtifacts(args.output / "audits")).execute(refs, registry, annotations, manifest["controls"], manifest["owner"])
    require(audit["controls_passed"] == audit["control_count"], "Semantic controls must pass before sealing")
    forecast = SealQualitativeQuestionExperiment(maps, FilePredictionStore(args.output / "runs")).execute(
        refs, registry, annotations, manifest["episodes"], manifest["question"], policy, manifest["owner"], args.analysis_scope)
    folder = args.output / "runs" / forecast["run_id"] / "review-v1"
    save_qualitative_review(folder, forecast, bundles, audit, previous, read(args.table_media)["sources"])
    receipt = {"run_id": forecast["run_id"], "report_folder": folder.as_posix(), "source_count": len(bundles),
               "study_families": len(forecast["binding"]["fold_plan"]), "claims": forecast["claim_count"], "controls_passed": audit["controls_passed"],
               "mode_counts": {k: len(v) for k, v in forecast["modes"].items()}, "readiness": forecast["readiness"], "model_calls": 0,
               "retrospective_folds": len(forecast["retrospective_folds"]), "future_target_read": False}
    write_immutable(args.output / "receipt-v1.json", FilePredictionStore.encode(receipt))
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == "__main__": main()

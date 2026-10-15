"""Конечные административные этапы ручного опыта: подготовка, обучение, gate, отдельная оценка."""
import argparse
import ctypes
import json
import logging
import os
import sys
from pathlib import Path

API = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API))
from domain.article_maps import require, parse_json_response, fingerprint
from application.prepare_research_bundle import prepare_bundle
from application.question_prediction import AuditResearchSemantics, SealQuestionForecast, EvaluateQuestionForecast
from infrastructure.prepared_research_maps import PreparedResearchMaps
from infrastructure.research_evaluation_maps import PreparedEvaluationMaps
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.research_artifacts import FileResearchArtifacts
from infrastructure.immutable_files import write_immutable
from infrastructure.question_prediction_report import save_report
from tools.import_codex_article_map import prohibit_generation


def read(path):
    return parse_json_response(path.read_text(encoding="utf-8"))


def bundles_from_manifest(manifest, parent):
    require(set(manifest) == {"bundles", "episodes", "question", "controls", "owner"}, "Source-only corpus manifest fields differ")
    require(isinstance(manifest["bundles"], list) and bool(manifest["bundles"]), "Explicit source bundle list required")
    return [read((parent / name).resolve()) for name in manifest["bundles"]]


def run(args):
    admin = bool(ctypes.windll.shell32.IsUserAnAdmin()) if sys.platform == "win32" else hasattr(os, "geteuid") and os.geteuid() == 0
    require(admin, "Administrative CLI required by AGENTS.md")
    prohibit_generation()
    if args.command == "prepare":
        if args.purpose == "evaluation":
            require(args.forecasts and args.run_id, "Sealed ready forecast required for target preparation")
            sealed = FilePredictionStore(args.forecasts).read_seal(args.run_id)
            require(sealed and sealed.get("readiness", {}).get("target_reading_allowed"), "Learning readiness failed; do not read target")
        metadata = read(args.metadata if args.metadata else args.source / "metadata.json")
        require(metadata.get("full_text_verified") is True, "Verify complete primary source before preparing knowledge")
        text = (args.source / "article.md").read_bytes().decode("utf-8")
        seed = read(args.seed)
        result = prepare_bundle(text, metadata, seed, args.purpose)
        write_immutable(args.destination, FilePredictionStore.encode(result))
        print(json.dumps({"bundle": str(args.destination), "run_id": result["map"]["run_id"], "model_calls": 0})); return
    manifest = read(args.manifest)
    bundles = bundles_from_manifest(manifest, args.manifest.parent)
    owner = manifest["owner"]
    maps = PreparedResearchMaps(bundles, owner, "training")
    refs = [{k: b["map"][k] for k in ("article_id", "pipeline_id", "run_id")} for b in bundles]
    registry = {b["map"]["article_id"]: b["registry"] for b in bundles}
    annotations = {b["map"]["article_id"]: b["annotation"] for b in bundles}
    store = FilePredictionStore(args.output)
    if args.command == "seal":
        audit = AuditResearchSemantics(maps, FileResearchArtifacts(args.output / "audits")).execute(refs, registry, annotations, manifest["controls"], owner)
        sealed = SealQuestionForecast(maps, store).execute(refs, registry, annotations, manifest["episodes"], manifest["question"], owner)
        save_report(args.output / sealed["run_id"] / "review-v4", audit, sealed)
        print(json.dumps({"run_id": sealed["run_id"], "audit_id": audit["audit_id"], "readiness": sealed["readiness"],
            "counts": {m: len(v) for m, v in sealed["modes"].items()}, "read_references": maps.reads, "model_calls": 0}, ensure_ascii=False)); return
    sealed = store.read_seal(args.run_id)
    require(sealed and sealed.get("readiness", {}).get("target_reading_allowed"), "Learning readiness failed; do not read target")
    require(sealed["binding"]["sources"] == refs and sealed["binding"]["owner"] == owner,
            "Evaluation training corpus differs from sealed corpus")
    # Файл цели читается впервые только после порога готовности и проверки запечатанного состава.
    bundle = read(args.target)
    require(bundle["origin"]["purpose"] == "evaluation", "Explicit evaluation bundle required")
    target = bundle["map"]
    result = EvaluateQuestionForecast(PreparedEvaluationMaps(maps, bundle, owner), store).execute(args.run_id,
        [{k: target[k] for k in ("article_id", "pipeline_id", "run_id")}],
        {target["article_id"]: bundle["registry"]}, {target["article_id"]: bundle["annotation"]}, owner)
    print(json.dumps({"evaluation_id": result["evaluation_id"], "model_calls": 0}))


def main():
    parser = argparse.ArgumentParser(description="Изолированный опыт по вопросу; модельные вызовы запрещены")
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    for name in ("source", "seed", "destination"): prepare.add_argument("--" + name, required=True, type=Path)
    prepare.add_argument("--purpose", required=True, choices=("training", "evaluation"))
    prepare.add_argument("--metadata", type=Path, help="Явная исправленная ревизия метаданных; исходная сохраняется")
    prepare.add_argument("--forecasts", type=Path); prepare.add_argument("--run-id")
    for name in ("seal", "evaluate"):
        command = commands.add_parser(name)
        command.add_argument("--manifest", required=True, type=Path); command.add_argument("--output", required=True, type=Path)
        if name == "evaluate":
            command.add_argument("--run-id", required=True); command.add_argument("--target", required=True, type=Path)
    logging.basicConfig(level=logging.INFO)
    run(parser.parse_args())


if __name__ == "__main__": main()

"""Административные процессы: контроль семантики, источники → seal, отдельная цель → оценка."""
from __future__ import annotations
import argparse
import ctypes
import json
import logging
import sys
from pathlib import Path

API = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API))
from domain.article_maps import parse_json_response, require, fingerprint
from application.question_prediction import AuditResearchSemantics, SealQuestionForecast, EvaluateQuestionForecast
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.research_artifacts import FileResearchArtifacts
from infrastructure.question_prediction_report import VERSION as REPORT_VERSION, save_report
from tools.import_codex_article_map import prohibit_generation
from tools.run_schema6_prediction import AuditedMaps, common_owner


def run(args):
    require(sys.platform == "win32" and bool(ctypes.windll.shell32.IsUserAnAdmin()), "Administrative CLI required by AGENTS.md")
    prohibit_generation()
    if args.command == "evaluate-bundle":
        from infrastructure.config import settings
        from infrastructure.neo4j.article_maps_repository import Neo4jArticleMapsRepository
        from infrastructure.research_evaluation_maps import PreparedEvaluationMaps
        store = FilePredictionStore(args.output)
        sealed = store.read_seal(args.run_id)
        require(sealed is not None, "Seal predictions before reading the prepared target")
        bundle = parse_json_response(args.bundle.read_text(encoding="utf-8"))
        repo = Neo4jArticleMapsRepository(settings.NEO4J_URI, settings.NEO4J_USER, settings.NEO4J_PASSWORD)
        try:
            owner = common_owner(repo, sealed["binding"]["sources"])
            m = bundle["map"]; article = m["article_id"]
            result = EvaluateQuestionForecast(PreparedEvaluationMaps(repo, bundle, owner), store).execute(args.run_id,
                [{"article_id": article, "pipeline_id": "text_reified", "run_id": m["run_id"]}],
                {article: bundle["registry"]}, {article: bundle["annotation"]}, owner)
            print(json.dumps({"evaluation_id": result["evaluation_id"], "relevant_target_claims": result["relevant_target_claims"],
                "target_origin": bundle["origin"], "model_calls": 0}, ensure_ascii=False))
        finally: repo.close()
        return
    if args.command == "report":
        sealed = FilePredictionStore(args.output).read_seal(args.run_id)
        require(sealed is not None, "Seal missing")
        audit = parse_json_response(args.audit.read_text(encoding="utf-8"))
        evaluation = parse_json_response(args.evaluation.read_text(encoding="utf-8")) if args.evaluation else None
        folder = args.output / args.run_id / (("evaluated-review" if evaluation else "sealed-review") + "-v" + REPORT_VERSION)
        save_report(folder, audit, sealed, evaluation)
        print(json.dumps({"report": str(folder), "run_id": args.run_id, "model_calls": 0})); return
    manifest = parse_json_response(args.manifest.read_text(encoding="utf-8"))
    required = {"references", "registry", "annotations"} | ({"controls"} if args.command == "audit" else {"episodes", "question"} if args.command == "seal" else set())
    require(set(manifest) == required, "Manifest fields differ; source process cannot receive evaluation data")
    from infrastructure.config import settings
    from infrastructure.neo4j.article_maps_repository import Neo4jArticleMapsRepository
    maps = Neo4jArticleMapsRepository(settings.NEO4J_URI, settings.NEO4J_USER, settings.NEO4J_PASSWORD)
    audited = AuditedMaps(maps)
    store = FilePredictionStore(args.output)
    try:
        refs = manifest["references"]
        owner = common_owner(maps, refs)
        if args.command == "audit":
            result = AuditResearchSemantics(audited, FileResearchArtifacts(args.output / "audits")).execute(
                refs, manifest["registry"], manifest["annotations"], manifest["controls"], owner)
            summary = {"audit_id": result["audit_id"], "controls_passed": result["controls_passed"], "control_count": result["control_count"]}
        elif args.command == "seal":
            result = SealQuestionForecast(audited, store).execute(refs, manifest["registry"], manifest["annotations"],
                manifest["episodes"], manifest["question"], owner)
            summary = {"run_id": result["run_id"], "prediction_sha256": fingerprint(result),
                       "counts": {k: len(v) for k, v in result["modes"].items()}, "diagnostics": result["diagnostics"]}
        else:
            result = EvaluateQuestionForecast(audited, store).execute(args.run_id, refs, manifest["registry"], manifest["annotations"], owner)
            summary = {"evaluation_id": result["evaluation_id"], "relevant_target_claims": result["relevant_target_claims"]}
        print(json.dumps({**summary, "read_references": audited.reads, "model_calls": 0}, ensure_ascii=False))
    finally: maps.close()


def main():
    parser = argparse.ArgumentParser(description="Прогноз только по заданному вопросу; генерация моделей запрещена")
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("audit", "seal", "evaluate"):
        cmd = commands.add_parser(command); cmd.add_argument("--manifest", required=True, type=Path); cmd.add_argument("--output", required=True, type=Path)
        if command == "evaluate": cmd.add_argument("--run-id", required=True)
    report = commands.add_parser("report"); report.add_argument("--output", required=True, type=Path)
    report.add_argument("--run-id", required=True); report.add_argument("--audit", required=True, type=Path); report.add_argument("--evaluation", type=Path)
    bundle = commands.add_parser("evaluate-bundle"); bundle.add_argument("--output", required=True, type=Path)
    bundle.add_argument("--run-id", required=True); bundle.add_argument("--bundle", required=True, type=Path)
    logging.basicConfig(level=logging.INFO)
    run(parser.parse_args())


if __name__ == "__main__": main()

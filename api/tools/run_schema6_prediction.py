"""Два административных процесса: источники → seal; seal + цель → оценка."""
from __future__ import annotations

import argparse
import ctypes
import json
import logging
import sys
from pathlib import Path

API = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API))
from application.development_prediction import SealSourcePrediction, EvaluateSourcePrediction
from domain.article_maps import require, fingerprint
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.article_comparison_controls import FixedComparisonControls
from tools.import_codex_article_map import prohibit_generation


class AuditedMaps:
    def __init__(self, maps):
        self.maps, self.driver, self.reads = maps, maps.driver, []

    def get(self, article, pipeline, user, run):
        self.reads.append({"article_id": article, "pipeline_id": pipeline, "run_id": run})
        return self.maps.get(article, pipeline, user, run)

    def authorize(self, article, user):
        return self.maps.authorize(article, user)


def common_owner(maps, references):
    owners = []
    with maps.driver.session() as session:
        for ref in references:
            row = session.run("MATCH (d:Document {uid:$id}) RETURN d.created_by_uid AS owner", id=ref["article_id"]).single()
            require(row is not None and bool(row["owner"]), "Source owner missing")
            owners.append(row["owner"])
    require(len(set(owners)) == 1, "All selected articles must have a common owner")
    return owners[0]


def run(args):
    prohibit_generation()
    require(bool(ctypes.windll.shell32.IsUserAnAdmin()), "Administrative CLI required by AGENTS.md")
    from infrastructure.config import settings
    from infrastructure.neo4j.article_maps_repository import Neo4jArticleMapsRepository
    store = FilePredictionStore(args.output)
    maps = Neo4jArticleMapsRepository(settings.NEO4J_URI, settings.NEO4J_USER, settings.NEO4J_PASSWORD)
    audited = AuditedMaps(maps)
    try:
        if args.command == "seal":
            # Этот процесс не принимает цель, контроль цитирования или её карту.
            sources = json.loads(args.sources.read_text(encoding="utf-8"))
            require(isinstance(sources, list), "Seal input must be a sources-only list")
            owner = common_owner(maps, sources)
            result = SealSourcePrediction(audited, store).execute(sources, owner)
            print(json.dumps({"sealed": True, "run_id": result["run_id"], "prediction_sha256": fingerprint(result),
                              "counts": {m: len(v) for m, v in result["predictions"].items()}, "diagnostics": result["diagnostics"],
                              "read_references": audited.reads, "model_calls": 0}))
        else:
            sealed = store.read_seal(args.run_id)
            require(sealed is not None, "Seal missing")
            target = json.loads(args.target.read_text(encoding="utf-8"))
            owner = common_owner(maps, [target, *sealed["binding"]["sources"]])
            result = EvaluateSourcePrediction(audited, store, FixedComparisonControls()).execute(args.run_id, target, owner)
            print(json.dumps({"evaluated": True, "evaluation_id": result["evaluation_id"],
                              "modes": {m: {k: v for k, v in stats.items() if k != "results"} for m, stats in result["modes"].items()},
                              "read_references": audited.reads, "model_calls": 0}))
    finally:
        maps.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    seal = commands.add_parser("seal"); seal.add_argument("--sources", required=True, type=Path); seal.add_argument("--output", required=True, type=Path)
    evaluate = commands.add_parser("evaluate"); evaluate.add_argument("--run-id", required=True); evaluate.add_argument("--target", required=True, type=Path); evaluate.add_argument("--output", required=True, type=Path)
    logging.basicConfig(level=logging.INFO)
    run(parser.parse_args())

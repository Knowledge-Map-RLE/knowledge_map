"""Преобразует первую GOLD-статью production-сценарием без изменения эталонов.

Запуск из api: poetry run python tools/run_text_to_map_gold.py --article-id PMC10000452
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
ROOT = API_ROOT.parent
sys.path.insert(0, str(API_ROOT))
sys.path.insert(0, str(ROOT / "shared" / "model_registry"))

from application.text_to_map import TextToMap
from domain.article_maps import digest, prepare_source, require
from domain.knowledge_map import model_contract, validate_knowledge_map
from domain.knowledge_map_schema import extraction_map_json_schema
from infrastructure.article_map_checkpoint import ExtractionCheckpointModel, write_checkpoint
from infrastructure.article_map_model import ArticleMapDependencyModelGateway, ArticleMapModelGateway
from infrastructure.article_map_source import StoredArticleMapSource
from infrastructure.config import settings
from infrastructure.neo4j.article_maps_repository import Neo4jArticleMapsRepository
from infrastructure.s3.s3_storage import get_s3_client


class RecordedModel:
    """Необязательная запись ответа для CLI-диагностики; содержимое не меняется."""
    def __init__(self, model, path, source_sha256, stage):
        self.model, self.path = model, path
        self.source_sha256, self.stage = source_sha256, stage

    @property
    def last_call(self):
        return self.model.last_call

    async def __call__(self, system, user):
        raw = await self.model(system, user)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(raw, encoding="utf-8")
        write_checkpoint(self.path, raw, system, user, self.source_sha256, self.model.last_call, stage=self.stage)
        return raw


async def run(article_id: str, response_artifact: Path | None = None,
              extraction_checkpoint: Path | None = None):
    gold_dir = Path(os.environ.get("ARTICLE_PIPELINE_GOLD_DIR", str(ROOT / "eval" / "article_pipeline_gold")))
    case = gold_dir / "cases" / "pmc10000452"
    metadata = json.loads((case / "meta.json").read_text(encoding="utf-8"))
    repo = Neo4jArticleMapsRepository(settings.NEO4J_URI, settings.NEO4J_USER, settings.NEO4J_PASSWORD,
                                    lease_seconds=2 * settings.LLM_TIMEOUT + 300)
    try:
        with repo.driver.session() as session:
            row = session.run("""MATCH (d:Document {uid:$id})
              RETURN d.created_by_uid AS owner,d.pmc_id AS pmc,d.gold_standard_source_pmc_id AS gold_pmc""",
              id=article_id).single()
        require(row is not None and bool(row["owner"]), "GOLD article or its owner was not found")
        require(article_id == metadata["document_uid"] or row["pmc"] == "PMC10000452"
                or row["gold_pmc"] == "PMC10000452", "Article does not correspond to the first GOLD case")
        owner = row["owner"]
        source = StoredArticleMapSource(repo, get_s3_client(), settings.S3_BUCKET_NAME)
        text = await source.read_text(article_id, owner)
        require(digest(text) == metadata["article_sha256"], "Saved article differs from the immutable English GOLD source")
        repo.ensure_schema()
        repo.migrate_legacy_snapshots(article_id)
        structural_before = repo.get(article_id, "structural_rows", owner)
        async def emit(event):
            print(json.dumps(event, ensure_ascii=False), flush=True)
        model = ArticleMapModelGateway(output_schema=extraction_map_json_schema(), strict_schema=True)
        dependencies = ArticleMapDependencyModelGateway()
        if extraction_checkpoint is not None:
            model = ExtractionCheckpointModel(extraction_checkpoint, digest(text))
        if response_artifact is not None:
            model = RecordedModel(model, response_artifact, digest(text), "extraction")
            dependencies = RecordedModel(dependencies, response_artifact.with_name(response_artifact.stem + "-dependencies.json"),
                                         digest(text), "dependencies")
        result = await TextToMap(repo, source, model, dependencies).execute(article_id, owner, emit)
        saved = repo.get(article_id, "text_reified", owner)
        require(saved == result, "Saved map does not match the validated result")
        stored_source = prepare_source(article_id, saved["source"]["text"])
        require(stored_source == saved["source"], "Saved source coordinates or fingerprint changed")
        # Повторно проверяем именно сохранённый граф, не только флаги в метаданных.
        require(validate_knowledge_map(model_contract(saved["graph"]), stored_source) == saved["graph"],
                "Saved graph does not pass independent contract, provenance and DAG validation")
        require(repo.get(article_id, "structural_rows", owner) == structural_before,
                "Structural map changed during text conversion")
        print(json.dumps({"success": True, "article_id": article_id, "pmc_id": "PMC10000452",
                          "pipeline_id": "text_reified", "run_id": result["run_id"],
                          "nodes": len(result["graph"]["nodes"]), "edges": len(result["graph"]["edges"]),
                          "assertions": sum(n["kind"] == "assertion" for n in result["graph"]["nodes"]),
                          "graph_schema_version": result["graph_schema_version"],
                          "analysis": result["graph"]["analysis"],
                          "source_sha256": stored_source["sha256"],
                          "validation": result["validation"], "expert_reviewed": False}, ensure_ascii=False), flush=True)
    finally:
        repo.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build the first GOLD article map through KM.TEXT_TO_MAP v2")
    parser.add_argument("--article-id", default="PMC10000452")
    parser.add_argument("--response-artifact", type=Path, help="Optional private JSON response artifact for diagnostics")
    parser.add_argument("--extraction-checkpoint", type=Path,
                        help="Explicitly resume a bound extraction checkpoint; dependency review always uses the LLM")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run(args.article_id, args.response_artifact, args.extraction_checkpoint))

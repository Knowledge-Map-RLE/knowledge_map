"""Административный CLI накопительного пилота, без старого извлечения строк."""
from __future__ import annotations

import argparse
import asyncio
import ctypes
import json
import logging
import os
import sys
from pathlib import Path
from uuid import UUID

API_ROOT = Path(__file__).resolve().parents[1]
ROOT = API_ROOT.parent
sys.path.insert(0, str(API_ROOT))
sys.path.insert(0, str(ROOT / "shared" / "model_registry"))

from application.reference_pilot import ReferencePilot
from domain.article_maps import require, digest, fingerprint
from domain.reference_prediction import source_priority
from infrastructure.article_map_source import StoredArticleMapSource
from infrastructure.config import settings
from infrastructure.neo4j.article_maps_repository import Neo4jArticleMapsRepository
from infrastructure.reference_pilot_builder import ProductionPilotMapBuilder
from infrastructure.article_map_model import ArticleMapModelGateway, ArticleMapDependencyModelGateway
from domain.knowledge_map_schema import extraction_map_json_schema
from infrastructure.reference_pilot_sources import EuropePmcSourceProvider
from infrastructure.reference_pilot_store import PilotStore, CachedStageModel
from infrastructure.s3.s3_storage import get_s3_client
from services.pdf_to_md_grpc_client import PDFToMarkdownGRPCClient
from services.xml_to_md_grpc_client import XmlToMdGRPCClient


async def execute(args):
    if os.name == "nt":
        require(bool(ctypes.windll.shell32.IsUserAnAdmin()), "Run this CLI as Administrator (AGENTS.md)")
    store = PilotStore(args.output)
    repository = Neo4jArticleMapsRepository(settings.NEO4J_URI, settings.NEO4J_USER, settings.NEO4J_PASSWORD,
                                           lease_seconds=2 * settings.LLM_TIMEOUT + 300)
    with repository.driver.session() as session:
        row = session.run("MATCH (d:Document {uid:$id}) RETURN d.created_by_uid AS owner", id=args.owner_article).single()
    require(row is not None and bool(row["owner"]), "Owner GOLD article was not found")
    owner = row["owner"]
    storage = get_s3_client()
    provider = EuropePmcSourceProvider(store, repository, storage, settings.S3_BUCKET_NAME, owner,
                                      XmlToMdGRPCClient(), PDFToMarkdownGRPCClient(), refresh_registry=args.refresh_registry)
    try:
        with store.lock():
            if args.command == "revalidate":
                require(bool(args.attempt_id), "Revalidation requires explicit --attempt-id")
                require(str(UUID(args.attempt_id)) == args.attempt_id, "Invalid attempt id")
                attempt = store.read(f"attempts/{args.attempt_id}.json")
                require(attempt is not None, "Original attempt not found")
                require(attempt["stage"] in {"extraction", "dependencies"},
                        "Explicit revalidation supports extraction and dependency stages")
                exact = store.read(f"requests/{attempt['stage']}/{attempt['cache_key']}.json")
                require(exact is not None, "Exact request not found")
                article_id = json.loads(exact["user"])["article_id"]
                reader = StoredArticleMapSource(repository, storage, settings.S3_BUCKET_NAME)
                text = await reader.read_text(article_id, owner)
                model = (ArticleMapModelGateway(output_schema=extraction_map_json_schema(), strict_schema=True)
                         if attempt["stage"] == "extraction" else ArticleMapDependencyModelGateway())
                receipt = CachedStageModel(model, store, text, stage=attempt["stage"]).revalidate_attempt(args.attempt_id)
                print(json.dumps(receipt, ensure_ascii=False), flush=True)
            elif args.command == "prepare":
                registry = await provider.registry()
                print(json.dumps({"references": len(registry["references"]),
                                  "open_access": sum(r["status"] == "open_access" for r in registry["references"]),
                                  "output": str(store.root)}, ensure_ascii=False), flush=True)
            elif args.command == "intake":
                registry = await provider.registry()
                by_number = {r["number"]: r for r in registry["references"]}
                references = [by_number[n] for n in registry["order"]
                              if by_number[n]["status"] == "open_access"][:args.size]
                sources = [await provider.materialize(reference) for reference in references]
                target = await provider.target()
                print(json.dumps({"sources": [{"source_id": s["source_id"], "article_id": s["article_id"]}
                                              for s in sources], "target_article": target["article_id"],
                                  "llm_calls": 0}, ensure_ascii=False), flush=True)
            else:
                repository.ensure_schema()
                if store.read("target/initial_existing_gold_map.json") is None:
                    initial = repository.get(args.owner_article, "text_reified", owner)
                    if initial is not None:
                        store.write("target/initial_existing_gold_map.json", initial)
                reader = StoredArticleMapSource(repository, storage, settings.S3_BUCKET_NAME)
                builder = ProductionPilotMapBuilder(repository, reader, owner, store, translate_ru=not args.no_translation)
                analysis_revision = fingerprint({name: digest((API_ROOT / name).read_text(encoding="utf-8"))
                                                 for name in ("domain/reference_prediction.py",
                                                              "application/reference_pilot.py")})
                for name in ("domain/reference_prediction.py", "application/reference_pilot.py"):
                    store.write_bytes(f"analysis/{analysis_revision}/{name}", (API_ROOT / name).read_bytes())
                report = await ReferencePilot(provider, builder, store, analysis_revision=analysis_revision,
                                              map_concurrency=args.map_concurrency).run(args.size)
                print(json.dumps({"success": True, "run_id": report["run_id"],
                                  "source_count": report["source_count"], "evaluation": {
                                      mode: {key: result[key] for key in ("predictions", "matched", "match_fraction")}
                                      for mode, result in report["evaluation"].items()},
                                  "report": str(store.path(f"runs/{report['run_id']}/report.ru.md")),
                                  "automatic_advance": False}, ensure_ascii=False), flush=True)
    finally:
        await provider.close()
        repository.close()


def parse_args():
    parser = argparse.ArgumentParser(description="Пилот PMC10000452: полный текст → карта знаний → символьный прогноз")
    parser.add_argument("command", choices=("prepare", "intake", "run", "revalidate"))
    parser.add_argument("--attempt-id", help="Явный id исходного ответа для повторной проверки новым валидатором")
    parser.add_argument("--size", type=int, default=5, help="Накопительное число источников; не более пяти новых за прогон")
    parser.add_argument("--map-concurrency", type=int, choices=range(1, 6), default=1,
                        help="Лимит одновременно строящихся карт; по умолчанию последовательный запуск")
    parser.add_argument("--owner-article", default="gold-pmc10000452")
    parser.add_argument("--output", type=Path, default=Path(os.environ.get(
        "REFERENCE_PILOT_DIR", str(ROOT / "eval" / "reference_pilots" / "pmc10000452"))))
    parser.add_argument("--no-translation", action="store_true", help="Не вызывать отдельный перевод подписей в этом прогоне")
    parser.add_argument("--refresh-registry", action="store_true", help="Явно создать новую ревизию библиографического реестра")
    return parser.parse_args()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    asyncio.run(execute(parse_args()))

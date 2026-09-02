"""
Layer: Frameworks & Drivers — Web
Package: web.app
Responsibility: Фабрика FastAPI-приложения — инициализация, middleware, роутеры.

Принадлежит слою Frameworks & Drivers. Это точка сборки: подключает все роутеры,
middleware, обработчики исключений и настраивает Neo4j.

Перемещено и переработано из src/app.py.
- Роутеры теперь из web/routers/ (тонкие контроллеры, вызывающие use cases)
- Обработчики доменных исключений зарегистрированы через web/exception_handlers.py
- GraphQL из adapters/graphql/schema.py (когда Фаза 4 будет выполнена)

Allowed imports: fastapi, neomodel.config, web.middleware, web.exception_handlers,
                 web.routers.*, infrastructure.config, adapters.graphql.schema
Forbidden imports: services (напрямую — только через web/routers и use cases)
"""
import logging
import os
from typing import Dict, Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from neomodel import config as neomodel_config

from infrastructure.config import settings
from web.middleware import ORIGINS, log_requests, add_cors_headers
from web.exception_handlers import register_exception_handlers

# Новые роутеры (чистая архитектура)
from web.routers import blocks, links, auth
from web.routers.data_extraction import annotations, annotations_ws, relations, documents as doc_router

# Роутеры из web/routers/ (новое расположение, TRANSITIONAL — скопированы из src/routers/)
from web.routers import pdf, layout, s3, ai_models, image_proxy, worker_status
from web.routers.data_extraction import (
    nlp as nlp_router,
    ontology as ontology_router,
    pubmed as pubmed_router,
    markdown_validation as markdown_validation_router,
    shared_actions as shared_actions_router,
)
# Статик роутер — оставляем из src (TRANSITIONAL)
from src.routers import static

# Прокси /ai/* -> AI Agent микросервис (OpenAI-совместимый, порт 50059)
from src.routers import ai_proxy as ai_proxy_router

# Персистентные AI-чаты (учёт токенов и стоимости)
from src.routers import ai_chats as ai_chats_router

# Редактор статей (article_editor + parse + graph)
from src.routers import article_editor as article_editor_router

# Социальная сеть (чат, друзья, сообщества, уведомления)
from src.routers import social_network as social_network_router

logger = logging.getLogger(__name__)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("api.log", encoding="utf-8"),
    ],
)

# Настройка Neo4j
database_url = settings.get_database_url()
neomodel_config.DATABASE_URL = database_url
if not settings.NEO4J_URI.startswith(("bolt+s://", "neo4j+s://")):
    neomodel_config.ENCRYPTED = False
logger.info(f"Neo4j: {settings.NEO4J_URI}")

# GraphQL из adapters/graphql/schema.py (Фаза 4 — чистая архитектура)
try:
    from adapters.graphql.schema import schema
    from strawberry.fastapi import GraphQLRouter
    graphql_app = GraphQLRouter(schema)
    _graphql_available = True
except Exception as e:
    logger.warning(f"GraphQL недоступен: {e}")
    _graphql_available = False

app = FastAPI(
    title="Knowledge Map API",
    description="API для карты знаний с конвертацией PDF",
    version="1.0.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,
)
app.middleware("http")(log_requests)
app.middleware("http")(add_cors_headers)

# Регистрируем обработчики доменных исключений
register_exception_handlers(app)

# ── Новые роутеры (чистая архитектура) ────────────────────────────────────────
app.include_router(blocks.router)
app.include_router(links.router)
app.include_router(auth.router)
app.include_router(annotations.router, prefix="/api/data_extraction")
app.include_router(annotations_ws.router, prefix="/api/data_extraction")
app.include_router(relations.router, prefix="/api/data_extraction")
app.include_router(doc_router.router, prefix="/api/data_extraction")

# ── Оставшиеся роутеры из web/routers/ ────────────────────────────────────────
app.include_router(pdf.router)
app.include_router(layout.router)
app.include_router(s3.router)
app.include_router(static.router)
app.include_router(ai_models.router, prefix="/api")
app.include_router(image_proxy.router)
# data_extraction sub-роутеры
app.include_router(nlp_router.router, prefix="/api/data_extraction")
app.include_router(ontology_router.router, prefix="/api/data_extraction")
app.include_router(pubmed_router.router, prefix="/api/data_extraction")
app.include_router(markdown_validation_router.router, prefix="/api/data_extraction")
app.include_router(shared_actions_router.router, prefix="/api/data_extraction")
app.include_router(worker_status.router, prefix="/api")

# Data download (загрузка данных из внешних источников)
from web.routers import data_download, data_download_ws
app.include_router(data_download.router, prefix="/api/data_download")
app.include_router(data_download_ws.router, prefix="/api/data_download")

# Паттерны (Action + LexicalUnit графы)
from web.routers.data_extraction import patterns as patterns_router
app.include_router(patterns_router.router, prefix="/api/data_extraction")

# Алгоритм уникальности знаний (uniqueness check, subgraph, pattern)
from web.routers.uniqueness import router as uniqueness_router
app.include_router(uniqueness_router)

# Лингвистические паттерны
from web.routers import linguistic as linguistic_router
app.include_router(linguistic_router.router)

# Лингвистический граф (Action + LexicalUnit)
from web.routers import pattern_graph as pattern_graph_router
app.include_router(pattern_graph_router.router)

# Выявление паттернов по графу утверждений (pattern-miner)
from web.routers.pattern_miner import router as pattern_miner_router
app.include_router(pattern_miner_router)

# Редактор статей (article_editor)
app.include_router(article_editor_router.router, prefix="/api")

# Текущий пользователь (роль из ADMIN_UIDS)
from src.routers import user as user_router
app.include_router(user_router.router, prefix="/api")

# Прокси AI Agent микросервиса (фронтенд -> API -> ai:50059)
app.include_router(ai_proxy_router.router)

# Персистентные AI-чаты (учёт токенов/стоимости, ownership, списание)
app.include_router(ai_chats_router.router)

# Социальная сеть (чат, друзья, сообщества, уведомления)
app.include_router(social_network_router.router, prefix="/api")

# GraphQL
if _graphql_available:
    app.include_router(graphql_app, prefix="/graphql")


@app.get("/health")
async def health_check() -> Dict[str, Any]:
    return {"status": "ok", "message": "API is healthy"}


@app.get("/")
async def root():
    return {
        "message": "Knowledge Map API",
        "graphql": "/graphql",
        "docs": "/docs",
    }


logger.info("Application startup complete.")


@app.on_event("startup")
async def _reset_stuck_documents():
    """Сбрасывает документы, зависшие в не-терминальных статусах после перезапуска."""
    try:
        from neomodel import db
        result, meta = db.cypher_query(
            "MATCH (d:Document) WHERE d.processing_status IN ['uploading', 'pdf_to_markdown'] "
            "SET d.processing_status = 'error' "
            "RETURN count(d) as count"
        )
        count = result[0][0] if result else 0
        if count:
            logger.warning(f"[startup] Сброшено {count} зависших документов в статус 'error'")
    except Exception as e:
        logger.warning(f"[startup] Не удалось сбросить зависшие документы: {e}")


@app.on_event("startup")
async def _ensure_document_indexes():
    """Создаёт индексы Neo4j для быстрого поиска документов."""
    INDEXES = [
        "CREATE INDEX IF NOT EXISTS FOR (d:Document) ON (d.uid)",
        "CREATE INDEX IF NOT EXISTS FOR (d:Document) ON (d.md5_hash)",
        "CREATE INDEX IF NOT EXISTS FOR (d:Document) ON (d.upload_date)",
        "CREATE INDEX IF NOT EXISTS FOR (d:Document) ON (d.processing_status)",
        "CREATE INDEX IF NOT EXISTS FOR (d:Document) ON (d.is_processed)",
        "CREATE INDEX IF NOT EXISTS FOR (d:Document) ON (d.source)",
        "CREATE INDEX IF NOT EXISTS FOR (d:Document) ON (d.pubmed_id)",
        "CREATE INDEX IF NOT EXISTS FOR (d:Document) ON (d.pmc_id)",
    ]
    try:
        from neomodel import db
        for cypher in INDEXES:
            try:
                db.cypher_query(cypher)
            except Exception as e:
                logger.warning(f"[startup] INDEX FAIL: {cypher[:60]}... {e}")

        # Fulltext-индекс: пересоздаём только если изменились поля ИЛИ индекс stale
        _DESIRED_FT_FIELDS = {"title", "original_filename", "doi", "pubmed_id", "pmc_id"}
        try:
            r, _ = db.cypher_query(
                "SHOW FULLTEXT INDEXES YIELD name, properties, state, populationPercent "
                "WHERE name = 'doc_fulltext' RETURN properties, state, populationPercent"
            )
            if r and r[0]:
                raw_fields = r[0][0] or []
                current_fields = {f.replace("d.", "") for f in raw_fields}
                idx_state = r[0][1]
                pop_pct = r[0][2]
            else:
                current_fields = set()
                idx_state = "MISSING"
                pop_pct = 0
            logger.info(f"[startup] Fulltext index state={idx_state} pop={pop_pct}% fields={current_fields}")
        except Exception:
            current_fields = set()
            idx_state = "MISSING"
            pop_pct = 0

        needs_rebuild = False
        if current_fields != _DESIRED_FT_FIELDS:
            logger.info(f"[startup] Fulltext index fields changed: {current_fields} -> {_DESIRED_FT_FIELDS}")
            needs_rebuild = True
        elif idx_state in ("MISSING", "FAILED"):
            logger.info(f"[startup] Fulltext index state={idx_state}, needs rebuild")
            needs_rebuild = True

        if needs_rebuild:
            logger.info("[startup] Recreating fulltext index...")
            try:
                db.cypher_query("DROP INDEX doc_fulltext IF EXISTS")
            except Exception:
                pass
            db.cypher_query(
                "CREATE FULLTEXT INDEX doc_fulltext "
                "FOR (d:Document) "
                "ON EACH [d.title, d.original_filename, d.doi, d.pubmed_id, d.pmc_id]"
            )
            logger.info("[startup] Fulltext index recreated (background population may take minutes)")
        else:
            logger.info("[startup] Fulltext index OK, skipping rebuild")
    except Exception as e:
        logger.warning(f"[startup] Не удалось создать индексы: {e}")


@app.on_event("startup")
async def _warm_counts_cache():
    """Прогревает кэши count_all/count_full_text при старте, чтобы первый запрос не висал 30+ сек."""
    import threading, time as _time
    def _warm():
        try:
            from adapters.repositories.document_repository import DocumentRepository
            repo = DocumentRepository()
            t0 = _time.monotonic()
            total = repo.count_all()
            dt = _time.monotonic() - t0
            logger.info(f"[startup] count_all warmed: {total} ({dt:.1f}s)")
            t0 = _time.monotonic()
            ft = repo.count_full_text()
            dt = _time.monotonic() - t0
            logger.info(f"[startup] count_full_text warmed: {ft} ({dt:.1f}s)")
            t0 = _time.monotonic()
            bs = repo.count_by_sources()
            dt = _time.monotonic() - t0
            logger.info(f"[startup] count_by_sources warmed: {bs} ({dt:.1f}s)")
        except Exception as e:
            logger.warning(f"[startup] Cache warmup failed: {e}")
    threading.Thread(target=_warm, daemon=True).start()


@app.on_event("startup")
async def _ensure_uniqueness_indexes():
    """Создаёт индексы Neo4j для алгоритма уникальности знаний."""
    UNIQUENESS_INDEXES = [
        "CREATE INDEX IF NOT EXISTS FOR (s:Statement) ON (s.fingerprint)",
        "CREATE INDEX IF NOT EXISTS FOR (sf:SubgraphFingerprint) ON (sf.wl_hash)",
        "CREATE INDEX IF NOT EXISTS FOR (sf:SubgraphFingerprint) ON (sf.id)",
    ]
    try:
        from neomodel import db
        for cypher in UNIQUENESS_INDEXES:
            try:
                db.cypher_query(cypher)
            except Exception as e:
                logger.warning(f"[startup] Uniqueness index failed: {cypher[:60]}... {e}")
        logger.info("[startup] Uniqueness indexes ensured")
    except Exception as e:
        logger.warning(f"[startup] Could not create uniqueness indexes: {e}")


@app.on_event("shutdown")
async def _close_ai_proxy_client():
    """Закрывает общий httpx-клиент прокси AI Agent микросервиса."""
    from src.routers.ai_proxy import close_client

    await close_client()

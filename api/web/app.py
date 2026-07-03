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
    actions as actions_router,
    pubmed as pubmed_router,
    markdown_validation as markdown_validation_router,
    auto_review_router,
    shared_actions as shared_actions_router,
)
# Статик роутер — оставляем из src (TRANSITIONAL)
from src.routers import static

# Редактор статей (article_editor + parse + graph)
from src.routers import article_editor as article_editor_router

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
app.include_router(actions_router.router, prefix="/api/data_extraction")
app.include_router(pubmed_router.router, prefix="/api/data_extraction")
app.include_router(markdown_validation_router.router, prefix="/api/data_extraction")
app.include_router(auto_review_router.router, prefix="/api/data_extraction")
app.include_router(shared_actions_router.router, prefix="/api/data_extraction")
app.include_router(worker_status.router, prefix="/api")

# Data download (загрузка данных из внешних источников)
from web.routers import data_download, data_download_ws
app.include_router(data_download.router, prefix="/api/data_download")
app.include_router(data_download_ws.router, prefix="/api/data_download")

# Паттерны (Action + LexicalUnit графы)
from web.routers.data_extraction import patterns as patterns_router
app.include_router(patterns_router.router, prefix="/api/data_extraction")

# Лингвистические паттерны
from web.routers import linguistic as linguistic_router
app.include_router(linguistic_router.router)

# Лингвистический граф (Action + LexicalUnit)
from web.routers import pattern_graph as pattern_graph_router
app.include_router(pattern_graph_router.router)

# Редактор статей (article_editor)
app.include_router(article_editor_router.router, prefix="/api")

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

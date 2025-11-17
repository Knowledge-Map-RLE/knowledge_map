"""Главное приложение FastAPI"""
import logging
import os
from typing import Dict, Any

from fastapi import FastAPI

# Отладочная информация о переменных окружения
logger = logging.getLogger(__name__)
logger.info(f"[app] Переменные окружения: PDF_TO_MD_SERVICE_HOST={os.getenv('PDF_TO_MD_SERVICE_HOST', 'НЕ УСТАНОВЛЕНА')}, PDF_TO_MD_SERVICE_PORT={os.getenv('PDF_TO_MD_SERVICE_PORT', 'НЕ УСТАНОВЛЕНА')}")
from fastapi.middleware.cors import CORSMiddleware
from strawberry.fastapi import GraphQLRouter

from services import settings
from neomodel import config as neomodel_config
from src.schema import schema

from src.middleware import ORIGINS, log_requests, add_cors_headers
from src.routers import (
    blocks, links, auth, data_extraction, pdf, layout, s3, static, ai_models
)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('api.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# Включаем детальное логирование
logging.getLogger('services.data_extraction_service').setLevel(logging.INFO)
logging.getLogger('services.pdf_to_md_client').setLevel(logging.INFO)

# Настройка подключения к Neo4j
neomodel_config.DATABASE_URL = settings.get_database_url()
neomodel_config.ENCRYPTED = False  # Явно отключаем TLS для Bolt
logger.info(f"Neo4j connection configured: {settings.NEO4J_URI}")

logger.info(f"Configuring CORS with origins: {ORIGINS}")

# Создаем приложение FastAPI
app = FastAPI(
    title="Knowledge Map API",
    description="API для карты знаний с конвертацией PDF",
    version="1.0.0"
)

# Настраиваем CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,  # Кэшируем CORS ответы на 1 час
)

# Middleware для логирования запросов
app.middleware("http")(log_requests)

# Middleware для добавления CORS заголовков
app.middleware("http")(add_cors_headers)

# Подключаем роутеры
app.include_router(blocks.router)
app.include_router(links.router)
app.include_router(auth.router)
app.include_router(data_extraction.router, prefix="/api/data_extraction")
app.include_router(pdf.router)
app.include_router(layout.router)
app.include_router(s3.router)
app.include_router(static.router)
app.include_router(ai_models.router, prefix="/api")

# Подключаем GraphQL
graphql_app = GraphQLRouter(schema)
app.include_router(graphql_app, prefix="/graphql")




# Эндпоинты для проверки здоровья
@app.get("/health")
async def health_check() -> Dict[str, Any]:
    """Проверяет здоровье API"""
    return {"status": "ok", "message": "API is healthy"}


@app.get("/")
async def root():
    return {
        "message": "Knowledge Map API", 
        "graphql": "/graphql",
        "docs": "/docs",
        "layout": "/layout/calculate",
        "layout_health": "/layout/health",
        "neo4j_browser": "http://localhost:7474"
    }


logger.info("Application startup complete.")

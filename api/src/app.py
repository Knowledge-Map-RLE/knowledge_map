"""Главное приложение FastAPI — TRANSITIONAL (будет удалён в Фазе 5).
Основной app теперь в web/app.py.
"""
import logging
import os
from typing import Dict, Any

from fastapi import FastAPI

logger = logging.getLogger(__name__)
from fastapi.middleware.cors import CORSMiddleware

from services import settings
from neomodel import config as neomodel_config

from src.middleware import ORIGINS, log_requests, add_cors_headers
from src.routers import (
    blocks, links, data_extraction, pdf, layout, s3, static, ai_models, image_proxy, article_editor
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
database_url = settings.get_database_url()
neomodel_config.DATABASE_URL = database_url
if not settings.NEO4J_URI.startswith(("bolt+s://", "neo4j+s://")):
    neomodel_config.ENCRYPTED = False  # Отключаем TLS только для локального Bolt

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
app.include_router(data_extraction.router, prefix="/api/data_extraction")
app.include_router(pdf.router)
app.include_router(layout.router)
app.include_router(s3.router)
app.include_router(static.router)
app.include_router(ai_models.router, prefix="/api")
app.include_router(image_proxy.router)
app.include_router(article_editor.router, prefix="/api")
from src.routers import user as user_router
app.include_router(user_router.router, prefix="/api")




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

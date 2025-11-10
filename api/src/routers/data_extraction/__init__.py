"""Главный роутер для извлечения данных из PDF и работы с аннотациями"""
import logging
from fastapi import APIRouter

# Импортируем все суб-роутеры
from . import documents, annotations, relations, nlp, csv_export

logger = logging.getLogger(__name__)

# Отладочная информация при импорте роутера
logger.info("[data_extraction_router] Импортируем data_extraction роутер")

# Создаём главный роутер
router = APIRouter(tags=["data_extraction"])

# Подключаем все суб-роутеры
router.include_router(documents.router, prefix="")
router.include_router(annotations.router, prefix="")
router.include_router(relations.router, prefix="")
router.include_router(nlp.router, prefix="")
router.include_router(csv_export.router, prefix="")

logger.info("[data_extraction_router] Все суб-роутеры подключены")

__all__ = ["router"]

"""Роутер для NLP анализа и автоаннотации"""
import logging
import asyncio
from fastapi import APIRouter, BackgroundTasks, HTTPException

from src.schemas.api import NLPAnalyzeRequest
from services.annotation_service import AnnotationService
from services.nlp_service import NLPService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["nlp"])
annotation_service = AnnotationService()
nlp_service = NLPService()


@router.post("/nlp/analyze")
async def analyze_text(request: NLPAnalyzeRequest):
    """
    NLP анализ текста с помощью spaCy
    Если указаны start и end, анализируется только выделенный фрагмент
    """
    try:
        if request.start is not None and request.end is not None:
            # Анализ выделенного фрагмента для подсказок
            return nlp_service.analyze_selection(request.text, request.start, request.end)
        else:
            # Полный анализ текста
            return nlp_service.analyze_text(request.text)
    except Exception as e:
        logger.error(f"Ошибка NLP анализа: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка NLP анализа: {str(e)}")


@router.post("/documents/{doc_id}/auto-annotate")
async def auto_annotate_document(
    doc_id: str,
    background_tasks: BackgroundTasks,
    processors: list[str] = ["spacy"],
    annotation_types: list[str] | None = None,
    min_confidence: float = 0.7
):
    """
    Автоматическая аннотация документа с помощью NLP процессоров.

    Args:
        doc_id: ID документа
        processors: Список процессоров для использования (по умолчанию: ["spacy"])
        annotation_types: Фильтр типов аннотаций (None = все типы)
        min_confidence: Минимальная уверенность модели (0.0-1.0)

    Returns:
        Количество созданных аннотаций и связей
    """
    try:
        result = await annotation_service.auto_annotate_document(
            doc_id=doc_id,
            processors=processors,
            annotation_types=annotation_types,
            min_confidence=min_confidence
        )
        return result
    except Exception as e:
        logger.error(f"Ошибка автоаннотации документа {doc_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка автоаннотации: {str(e)}")


@router.post("/documents/{doc_id}/auto-annotate/batch")
async def auto_annotate_batch(
    doc_id: str,
    background_tasks: BackgroundTasks,
    processors: list[str] = ["spacy"],
    annotation_types: list[str] | None = None,
    min_confidence: float = 0.7,
    chunk_size: int = 5000
):
    """
    Фоновая автоаннотация большого документа частями.

    Args:
        doc_id: ID документа
        processors: Список процессоров
        annotation_types: Фильтр типов
        min_confidence: Минимальная уверенность
        chunk_size: Размер чанка для обработки

    Returns:
        Сообщение о запуске фоновой задачи
    """

    def process_in_background():
        try:
            logger.info(f"Запуск фоновой автоаннотации документа {doc_id}")
            # Синхронная версия для фоновой задачи
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(
                annotation_service.auto_annotate_document(
                    doc_id=doc_id,
                    processors=processors,
                    annotation_types=annotation_types,
                    min_confidence=min_confidence
                )
            )
            logger.info(f"Фоновая автоаннотация завершена: {result}")
        except Exception as e:
            logger.error(f"Ошибка в фоновой автоаннотации: {e}")

    background_tasks.add_task(process_in_background)

    return {
        "success": True,
        "message": f"Автоаннотация документа {doc_id} запущена в фоне",
        "doc_id": doc_id
    }


@router.get("/nlp/supported-types")
async def get_supported_types():
    """
    Получить все поддерживаемые типы аннотаций от всех процессоров.

    Returns:
        Словарь категорий и типов аннотаций
    """
    try:
        return nlp_service.get_all_supported_types()
    except Exception as e:
        logger.error(f"Ошибка получения поддерживаемых типов: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка: {str(e)}")

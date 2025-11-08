"""Роутер для извлечения данных из PDF"""
import logging
from typing import Dict, Any, Optional

from fastapi import APIRouter, BackgroundTasks, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse

from src.schemas.api import (
    DataExtractionResponse, ImportAnnotationsRequest, DocumentAssetsResponse,
    UpdateMarkdownRequest, UpdateMarkdownResponse,
    CreateAnnotationRequest, UpdateAnnotationRequest, AnnotationResponse,
    CreateRelationRequest, RelationResponse, NLPAnalyzeRequest,
    BatchUpdateOffsetsRequest, BatchUpdateOffsetsResponse
)
from services.data_extraction_service import DataExtractionService
from services.annotation_service import AnnotationService
from services.nlp_service import NLPService

logger = logging.getLogger(__name__)

# Отладочная информация при импорте роутера
logger.info("[data_extraction_router] Импортируем data_extraction роутер")

router = APIRouter(tags=["data_extraction"])
data_extraction_service = DataExtractionService()
annotation_service = AnnotationService()
nlp_service = NLPService()

logger.info("[data_extraction_router] DataExtractionService, AnnotationService и NLPService созданы")


@router.post("/data_extraction", response_model=DataExtractionResponse)
async def data_extraction_upload(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """Загрузка PDF, MD5-дедупликация, Marker→Markdown, загрузка md+изображений+json в S3."""
    return await data_extraction_service.upload_and_process_pdf(background_tasks, file)


@router.get("/annotations/export")
async def export_annotations(doc_id: str):
    """Экспорт аннотаций"""
    return await data_extraction_service.export_annotations(doc_id)


@router.post("/annotations/import")
async def import_annotations(payload: ImportAnnotationsRequest):
    """Импорт аннотаций"""
    return await data_extraction_service.import_annotations(payload)


@router.get("/documents/{doc_id}/assets", response_model=DocumentAssetsResponse)
async def get_document_assets(doc_id: str, include_urls: bool = True):
    """Возвращает markdown и список изображений (ключей) для документа."""
    result = await data_extraction_service.get_document_assets(doc_id, include_urls=include_urls)
    return DocumentAssetsResponse(**result)


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str):
    """Удаляет документ и все его файлы из S3 (префикс documents/{doc_id}/)."""
    return await data_extraction_service.delete_document(doc_id)


@router.get("/documents")
async def list_documents():
    """Список документов по префиксу documents/ из S3."""
    return await data_extraction_service.list_documents()


@router.put("/documents/{doc_id}/markdown", response_model=UpdateMarkdownResponse)
async def update_document_markdown(doc_id: str, request: UpdateMarkdownRequest):
    """Обновляет markdown документа в S3."""
    try:
        result = await data_extraction_service.update_markdown(doc_id, request.markdown)
        return UpdateMarkdownResponse(**result)
    except Exception as e:
        logger.error(f"Ошибка обновления markdown: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/documents/{doc_id}/images/{image_name}")
async def get_document_image(doc_id: str, image_name: str):
    """Получает изображение документа из S3."""
    from fastapi.responses import Response
    from services import get_s3_client, settings

    try:
        s3_client = get_s3_client()
        bucket = settings.S3_BUCKET_NAME
        image_key = f"documents/{doc_id}/{image_name}"

        if not await s3_client.object_exists(bucket, image_key):
            raise HTTPException(status_code=404, detail="Изображение не найдено")

        image_data = await s3_client.download_bytes(bucket, image_key)
        if not image_data:
            raise HTTPException(status_code=500, detail="Не удалось загрузить изображение")

        # Определяем content-type по расширению файла
        content_type = "image/jpeg"
        if image_name.lower().endswith('.png'):
            content_type = "image/png"
        elif image_name.lower().endswith('.gif'):
            content_type = "image/gif"
        elif image_name.lower().endswith('.bmp'):
            content_type = "image/bmp"

        return Response(content=image_data, media_type=content_type)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка получения изображения: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== ENDPOINTS ДЛЯ АННОТАЦИЙ MARKDOWN ====================

@router.post("/documents/{doc_id}/annotations", response_model=AnnotationResponse)
async def create_annotation(doc_id: str, request: CreateAnnotationRequest):
    """Создать новую аннотацию для документа"""
    return await annotation_service.create_annotation(
        doc_id=doc_id,
        text=request.text,
        annotation_type=request.annotation_type,
        start_offset=request.start_offset,
        end_offset=request.end_offset,
        color=request.color,
        user_id=request.user_id,
        metadata=request.metadata,
        confidence=request.confidence
    )


@router.get("/documents/{doc_id}/annotations")
async def get_annotations(
    doc_id: str,
    skip: int = 0,
    limit: Optional[int] = None,
    annotation_types: Optional[str] = None,
    source: Optional[str] = None
):
    """
    Получить аннотации документа с пагинацией и фильтрацией

    Args:
        doc_id: ID документа
        skip: Количество пропускаемых аннотаций
        limit: Максимальное количество возвращаемых аннотаций
        annotation_types: Фильтр по типам (через запятую)
        source: Фильтр по источнику (user/spacy/custom)
    """
    # Парсим типы аннотаций из строки
    types_list = annotation_types.split(',') if annotation_types else None

    return await annotation_service.get_annotations(
        doc_id=doc_id,
        skip=skip,
        limit=limit,
        annotation_types=types_list,
        source=source
    )


@router.put("/annotations/{annotation_id}", response_model=AnnotationResponse)
async def update_annotation(annotation_id: str, request: UpdateAnnotationRequest):
    """Обновить существующую аннотацию"""
    return await annotation_service.update_annotation(
        annotation_id=annotation_id,
        text=request.text,
        annotation_type=request.annotation_type,
        start_offset=request.start_offset,
        end_offset=request.end_offset,
        color=request.color,
        metadata=request.metadata
    )


@router.delete("/annotations/{annotation_id}")
async def delete_annotation(annotation_id: str):
    """Удалить аннотацию"""
    return await annotation_service.delete_annotation(annotation_id)


@router.post("/annotations/batch-update-offsets", response_model=BatchUpdateOffsetsResponse)
async def batch_update_offsets(request: BatchUpdateOffsetsRequest):
    """Массовое обновление offset аннотаций при редактировании текста"""
    updates = [update.dict() for update in request.updates]
    return await annotation_service.batch_update_offsets(updates)


# ==================== ENDPOINTS ДЛЯ СВЯЗЕЙ МЕЖДУ АННОТАЦИЯМИ ====================

@router.post("/annotations/{source_id}/relations", response_model=RelationResponse)
async def create_relation(source_id: str, request: CreateRelationRequest):
    """Создать связь между двумя аннотациями"""
    return await annotation_service.create_relation(
        source_id=source_id,
        target_id=request.target_id,
        relation_type=request.relation_type,
        metadata=request.metadata
    )


@router.delete("/annotations/{source_id}/relations/{target_id}")
async def delete_relation(source_id: str, target_id: str):
    """Удалить связь между аннотациями"""
    return await annotation_service.delete_relation(source_id, target_id)


@router.get("/documents/{doc_id}/relations")
async def get_relations(doc_id: str):
    """Получить все связи между аннотациями документа"""
    return await annotation_service.get_relations(doc_id)


# ==================== ENDPOINTS ДЛЯ NLP АНАЛИЗА ====================

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
            import asyncio
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
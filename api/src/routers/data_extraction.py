"""Роутер для извлечения данных из PDF"""
import logging
from typing import Dict, Any

from fastapi import APIRouter, BackgroundTasks, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse

from src.schemas.api import (
    DataExtractionResponse, ImportAnnotationsRequest, DocumentAssetsResponse,
    UpdateMarkdownRequest, UpdateMarkdownResponse
)
from services.data_extraction_service import DataExtractionService

logger = logging.getLogger(__name__)

# Отладочная информация при импорте роутера
logger.info("[data_extraction_router] Импортируем data_extraction роутер")

router = APIRouter(tags=["data_extraction"])
data_extraction_service = DataExtractionService()

logger.info("[data_extraction_router] DataExtractionService создан")


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
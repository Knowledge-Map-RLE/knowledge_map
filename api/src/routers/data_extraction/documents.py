"""Роутер для работы с документами"""
import logging
from fastapi import APIRouter, BackgroundTasks, UploadFile, File, HTTPException
from fastapi.responses import Response

from src.schemas.api import (
    DataExtractionResponse,
    DocumentAssetsResponse,
    UpdateMarkdownRequest,
    UpdateMarkdownResponse,
    SaveForTestsRequest,
    SaveForTestsResponse,
    DataAvailabilityStatus,
)
from services.data_extraction_service import DataExtractionService
from services import get_s3_client, settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["documents"])
data_extraction_service = DataExtractionService()


@router.post("/data_extraction", response_model=DataExtractionResponse)
async def data_extraction_upload(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """Загрузка PDF, MD5-дедупликация, конвертация в Markdown, загрузка md+изображений+json в S3."""
    return await data_extraction_service.upload_and_process_pdf(background_tasks, file)


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


@router.get("/documents/{doc_id}/markdown")
async def get_document_markdown(doc_id: str, version: str = "active"):
    """
    Получает markdown документа из S3.

    Args:
        doc_id: ID документа
        version: Версия markdown файла
            - "active" (default): возвращает user версию если есть, иначе formatted, иначе raw
            - "raw": возвращает raw Docling markdown
            - "formatted": возвращает AI-форматированный markdown
            - "user": возвращает пользовательскую версию
    """
    try:
        result = await data_extraction_service.get_markdown(doc_id, version=version)
        return Response(
            content=result["markdown"].encode('utf-8'),
            media_type="text/markdown; charset=utf-8"
        )
    except Exception as e:
        logger.error(f"Ошибка получения markdown: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/documents/{doc_id}/images/{image_name}")
async def get_document_image(doc_id: str, image_name: str):
    """Получает изображение документа из S3."""
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


@router.get("/documents/{doc_id}/data-availability", response_model=DataAvailabilityStatus)
async def check_document_data_availability(doc_id: str):
    """
    Проверяет доступность данных документа для экспорта в тестовый датасет.

    Возвращает информацию о наличии PDF, Markdown, аннотаций, связей, цепочек и паттернов.
    """
    try:
        result = await data_extraction_service.check_data_availability(doc_id)
        return DataAvailabilityStatus(**result)
    except Exception as e:
        logger.error(f"Ошибка проверки доступности данных: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/documents/{doc_id}/save-for-tests", response_model=SaveForTestsResponse)
async def save_document_for_tests(doc_id: str, request: SaveForTestsRequest):
    """
    Экспортирует документ с аннотациями, связями и цепочками в тестовый датасет.

    Документ должен иметь PDF, Markdown и хотя бы одну аннотацию для успешного экспорта.
    Экспортированные данные сохраняются в ./data/datasets/ и могут быть версионированы через DVC.
    """
    try:
        # Сначала проверяем доступность данных
        availability = await data_extraction_service.check_data_availability(doc_id)

        if not availability["is_ready"]:
            missing = ", ".join(availability["missing_items"])
            raise HTTPException(
                status_code=400,
                detail=f"Документ не готов к экспорту. Отсутствуют: {missing}. "
                       f"Данные попадут в тестовый датасет только после прохождения всех этапов обработки."
            )

        # Выполняем экспорт (PDF, patterns и chains всегда обязательны)
        # Имя датасета генерируется автоматически
        result = await data_extraction_service.save_for_tests(
            doc_id=doc_id,
            validate=request.validate
        )

        if not result["success"]:
            raise HTTPException(status_code=500, detail=result.get("message", "Ошибка экспорта"))

        return SaveForTestsResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка сохранения для тестов: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

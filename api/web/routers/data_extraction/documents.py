"""
Layer: Interface Adapters — Controller (Web)
Package: web.routers.data_extraction.documents
Responsibility: HTTP route handlers для загрузки и управления PDF-документами.

Тонкий контроллер: парсит запрос → вызывает use case → возвращает ответ.
Длинная бизнес-логика (конвертация PDF → MD, валидация) делегирована в application/.

Allowed imports: fastapi, application.documents.*, web.dependencies, src.schemas.api
Forbidden imports: neomodel (напрямую), services (напрямую), infrastructure (напрямую)
"""
import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, UploadFile, File, Request, Query
from fastapi.responses import Response

from src.schemas.api import (
    DataExtractionResponse,
    DocumentAssetsResponse,
    UpdateMarkdownRequest,
    UpdateMarkdownResponse,
)
from application.documents.upload_pdf import upload_pdf
from application.documents.get_document_assets import get_document_assets
from application.documents.delete_document import delete_document
from application.documents.list_documents import list_documents
from application.documents.get_markdown import get_markdown
from application.documents.update_markdown import update_markdown
from web.dependencies import get_document_repository, get_s3

from utils.hash_utils import _compute_md5
from infrastructure.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["documents"])


@router.post("/data_extraction", response_model=DataExtractionResponse)
async def data_extraction_upload(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    doc_repo=Depends(get_document_repository),
    storage=Depends(get_s3),
):
    """Загружает PDF, выполняет MD5-дедупликацию и запускает конвертацию в Markdown."""
    from services.data_extraction_service import DataExtractionService  # TRANSITIONAL
    svc = DataExtractionService()
    result = await svc.upload_and_process_pdf(background_tasks, file)
    return result


@router.get("/documents/{doc_id}/assets", response_model=DocumentAssetsResponse)
async def get_document_assets_route(
    doc_id: str,
    request: Request,
    include_urls: bool = True,
    doc_repo=Depends(get_document_repository),
    storage=Depends(get_s3),
):
    """Возвращает markdown и список изображений документа."""
    result = await get_document_assets(
        document_repo=doc_repo,
        storage=storage,
        doc_id=doc_id,
    )
    return DocumentAssetsResponse(success=True, **result)


@router.delete("/documents/{doc_id}")
async def delete_document_route(
    doc_id: str,
    doc_repo=Depends(get_document_repository),
    storage=Depends(get_s3),
):
    """Удаляет документ и все его файлы из S3."""
    await delete_document(document_repo=doc_repo, storage=storage, doc_id=doc_id)
    return {"success": True, "message": f"Document {doc_id} deleted"}


@router.get("/documents")
async def list_documents_route(doc_repo=Depends(get_document_repository)):
    """Список документов из Neo4j."""
    docs = list_documents(repo=doc_repo)
    return {
        "success": True,
        "documents": [
            {
                "doc_id": d.uid,
                "title": d.title,
                "original_filename": d.original_filename,
                "processing_status": d.processing_status,
                "is_processed": d.is_processed,
                "source": d.source,
                "has_markdown": d.get_active_markdown_key() is not None,
                "pubmed_id": d.pubmed_id,
                "pmc_id": d.pmc_id,
                "files": {"pdf": f"/api/v1/s3/image/{d.s3_key}"} if d.s3_key else {},
            }
            for d in docs
        ],
    }


@router.put("/documents/{doc_id}/markdown", response_model=UpdateMarkdownResponse)
async def update_document_markdown(
    doc_id: str,
    request_body: UpdateMarkdownRequest,
    doc_repo=Depends(get_document_repository),
    storage=Depends(get_s3),
):
    """Обновляет markdown документа с опциональной валидацией."""
    validation_result = None

    # Авто-валидация через NLP сервис (делегируем через старый сервис — TRANSITIONAL)
    if request_body.auto_validate:
        try:
            from services.nlp_grpc_client import get_nlp_grpc_client
            grpc_client = get_nlp_grpc_client()
            validation_result = await grpc_client.validate_markdown(
                markdown=request_body.markdown,
                strict_mode=request_body.strict_mode,
            )
            if request_body.strict_mode and not validation_result.get("is_valid"):
                from fastapi import HTTPException
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": f"Валидация не пройдена: {validation_result.get('total_errors')} ошибок",
                        "validation": validation_result,
                    },
                )
        except Exception as e:
            logger.warning(f"[documents] Валидация markdown не удалась: {e}")

    result = await update_markdown(
        document_repo=doc_repo,
        storage=storage,
        doc_id=doc_id,
        markdown=request_body.markdown,
        bucket=settings.S3_BUCKET_NAME,
    )
    return UpdateMarkdownResponse(
        success=True,
        doc_id=doc_id,
        s3_key=result["s3_key"],
        title=result.get("title"),
        validation=validation_result,
    )


@router.get("/documents/{doc_id}/progress")
async def get_document_progress_route(
    doc_id: str,
    doc_repo=Depends(get_document_repository),
):
    """Возвращает текущий прогресс конвертации документа."""
    from services.data_extraction_service import _conversion_progress
    doc = doc_repo.get_by_id(doc_id)
    progress = _conversion_progress.get(doc_id, {})
    return {
        "doc_id": doc_id,
        "processing_status": doc.processing_status if doc else "unknown",
        "percent": progress.get("percent", 0),
        "phase": progress.get("phase", ""),
        "message": progress.get("message", ""),
    }


@router.get("/documents/{doc_id}/markdown")
async def get_document_markdown(
    doc_id: str,
    version: str = Query("active", pattern="^(active|raw|formatted|user)$"),
    doc_repo=Depends(get_document_repository),
    storage=Depends(get_s3),
):
    """Возвращает markdown выбранной версии."""
    content = await get_markdown(
        document_repo=doc_repo,
        storage=storage,
        doc_id=doc_id,
        version=version,
    )
    if content is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Markdown version '{version}' not found")
    return Response(content=content, media_type="text/markdown")

"""Роутер для извлечения данных из PDF"""
import logging
from typing import Dict, Any

from fastapi import APIRouter, BackgroundTasks, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse

from src.schemas.api import (
    DataExtractionResponse, ImportAnnotationsRequest, DocumentAssetsResponse
)
from services.data_extraction_service import DataExtractionService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["data_extraction"])
data_extraction_service = DataExtractionService()


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

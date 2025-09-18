"""Роутер для работы с PDF документами"""
import logging
from typing import List, Dict, Any

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import Response

from src.schemas.pdf import (
    PDFUploadResponse, PDFDocumentResponse, PDFAnnotationResponse
)
from services.pdf_service import PDFService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/pdf", tags=["pdf"])
pdf_service = PDFService()


@router.post("/upload", response_model=PDFUploadResponse)
async def upload_pdf(
    file: UploadFile = File(...),
    user_id: str = Form(...)
):
    """Загружает PDF файл в S3 и создает запись в Neo4j"""
    return await pdf_service.upload_pdf(file, user_id)


@router.get("/documents", response_model=List[PDFDocumentResponse])
async def get_pdf_documents(user_id: str):
    """Получает список PDF документов пользователя"""
    return await pdf_service.get_pdf_documents(user_id)


@router.get("/document/{document_id}", response_model=PDFDocumentResponse)
async def get_pdf_document(document_id: str):
    """Получает информацию о PDF документе"""
    return await pdf_service.get_pdf_document(document_id)


@router.get("/document/{document_id}/view")
async def view_pdf_document(document_id: str):
    """Просматривает PDF документ в браузере"""
    return await pdf_service.view_pdf_document(document_id)


@router.get("/document/{document_id}/download")
async def download_pdf_document(document_id: str):
    """Скачивает PDF документ из S3"""
    return await pdf_service.download_pdf_document(document_id)


@router.get("/document/{document_id}/annotations", response_model=List[PDFAnnotationResponse])
async def get_pdf_annotations(document_id: str):
    """Получает аннотации PDF документа"""
    return await pdf_service.get_pdf_annotations(document_id)


@router.post("/document/{document_id}/annotate")
async def start_pdf_annotation(document_id: str, user_id: str = Form(...)):
    """Запускает процесс автоматической аннотации PDF документа"""
    return await pdf_service.start_pdf_annotation(document_id, user_id)


@router.post("/document/{document_id}/reset")
async def reset_document_status(document_id: str):
    """Сбрасывает статус документа для повторной обработки"""
    return await pdf_service.reset_document_status(document_id)


@router.delete("/document/{document_id}")
async def delete_document(document_id: str):
    """Удаляет документ из системы"""
    return await pdf_service.delete_document(document_id)

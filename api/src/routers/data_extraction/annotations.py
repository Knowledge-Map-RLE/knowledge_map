"""Роутер для работы с аннотациями"""
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException

from src.schemas.api import (
    CreateAnnotationRequest,
    UpdateAnnotationRequest,
    AnnotationResponse,
    BatchUpdateOffsetsRequest,
    BatchUpdateOffsetsResponse,
)
from services.annotation_service import AnnotationService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["annotations"])
annotation_service = AnnotationService()


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
        source: Фильтр по источнику (user/spacy/custom/file)
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


@router.delete("/documents/{doc_id}/annotations/all")
async def delete_all_document_annotations(doc_id: str):
    """Удалить все аннотации документа"""
    return await annotation_service.delete_all_annotations(doc_id)


@router.post("/annotations/batch-update-offsets", response_model=BatchUpdateOffsetsResponse)
async def batch_update_offsets(request: BatchUpdateOffsetsRequest):
    """Массовое обновление offset аннотаций при редактировании текста"""
    updates = [update.dict() for update in request.updates]
    return await annotation_service.batch_update_offsets(updates)

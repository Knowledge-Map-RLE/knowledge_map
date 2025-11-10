"""Роутер для работы со связями между аннотациями"""
import logging
from fastapi import APIRouter

from src.schemas.api import CreateRelationRequest, RelationResponse
from services.annotation_service import AnnotationService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["relations"])
annotation_service = AnnotationService()


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

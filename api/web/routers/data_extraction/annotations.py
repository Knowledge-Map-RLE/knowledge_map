"""
Layer: Interface Adapters — Controller (Web)
Package: web.routers.data_extraction.annotations
Responsibility: HTTP route handlers для Markdown-аннотаций. Тонкий контроллер.

Allowed imports: fastapi, application.annotations.*, application.relations.*,
                 web.dependencies, src.schemas.api
Forbidden imports: neomodel (напрямую), services (напрямую), infrastructure
"""
import logging
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, Depends, Query

from src.schemas.api import (
    CreateAnnotationRequest,
    UpdateAnnotationRequest,
    BatchUpdateOffsetsRequest,
    AnnotationResponse,
    BatchUpdateOffsetsResponse,
)
from application.annotations.create_annotation import create_annotation
from application.annotations.get_annotations import get_annotations
from application.annotations.update_annotation import update_annotation
from application.annotations.delete_annotation import delete_annotation, delete_all_annotations
from application.annotations.batch_update_offsets import batch_update_offsets
from web.dependencies import get_annotation_repository, get_document_repository

logger = logging.getLogger(__name__)

router = APIRouter(tags=["annotations"])


def _annotation_to_response(ann) -> Dict[str, Any]:
    return {
        "uid": ann.uid,
        "text": ann.text,
        "annotation_type": ann.annotation_type,
        "start_offset": ann.start_offset,
        "end_offset": ann.end_offset,
        "color": ann.color,
        "metadata": ann.metadata or {},
        "confidence": ann.confidence,
        "created_date": str(ann.created_date) if ann.created_date else None,
        "source": ann.source,
        "processor_version": ann.processor_version,
    }


@router.post("/documents/{doc_id}/annotations", response_model=Dict[str, Any])
async def create_annotation_route(
    doc_id: str,
    request: CreateAnnotationRequest,
    ann_repo=Depends(get_annotation_repository),
    doc_repo=Depends(get_document_repository),
):
    ann = create_annotation(
        annotation_repo=ann_repo,
        document_repo=doc_repo,
        doc_id=doc_id,
        text=request.text,
        annotation_type=request.annotation_type,
        start_offset=request.start_offset,
        end_offset=request.end_offset,
        color=request.color,
        metadata=request.metadata,
        confidence=request.confidence,
        source="user",
    )
    return {"success": True, "annotation": _annotation_to_response(ann)}


@router.get("/documents/{doc_id}/annotations", response_model=Dict[str, Any])
async def get_annotations_route(
    doc_id: str,
    skip: int = Query(0, ge=0),
    limit: Optional[int] = Query(None, ge=1),
    annotation_types: Optional[List[str]] = Query(None),
    source: Optional[str] = Query(None),
    ann_repo=Depends(get_annotation_repository),
    doc_repo=Depends(get_document_repository),
):
    anns, total = get_annotations(
        annotation_repo=ann_repo,
        document_repo=doc_repo,
        doc_id=doc_id,
        skip=skip,
        limit=limit,
        annotation_types=annotation_types,
        source=source,
    )
    return {
        "success": True,
        "annotations": [_annotation_to_response(a) for a in anns],
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.put("/annotations/{annotation_id}", response_model=Dict[str, Any])
async def update_annotation_route(
    annotation_id: str,
    request: UpdateAnnotationRequest,
    ann_repo=Depends(get_annotation_repository),
):
    ann = update_annotation(
        repo=ann_repo,
        annotation_id=annotation_id,
        text=request.text,
        annotation_type=request.annotation_type,
        start_offset=request.start_offset,
        end_offset=request.end_offset,
        color=request.color,
        metadata=request.metadata,
    )
    return {"success": True, "annotation": _annotation_to_response(ann)}


@router.delete("/annotations/{annotation_id}", response_model=Dict[str, Any])
async def delete_annotation_route(
    annotation_id: str,
    ann_repo=Depends(get_annotation_repository),
):
    delete_annotation(repo=ann_repo, annotation_id=annotation_id)
    return {"success": True, "message": f"Annotation {annotation_id} deleted"}


@router.delete("/documents/{doc_id}/annotations/all", response_model=Dict[str, Any])
async def delete_all_annotations_route(
    doc_id: str,
    ann_repo=Depends(get_annotation_repository),
    doc_repo=Depends(get_document_repository),
):
    count = delete_all_annotations(
        annotation_repo=ann_repo, document_repo=doc_repo, doc_id=doc_id
    )
    return {"success": True, "deleted_count": count}


@router.post("/annotations/batch-update-offsets", response_model=BatchUpdateOffsetsResponse)
async def batch_update_offsets_route(
    request: BatchUpdateOffsetsRequest,
    ann_repo=Depends(get_annotation_repository),
):
    updates = [u.model_dump() for u in request.updates]
    updated_count, errors = batch_update_offsets(repo=ann_repo, updates=updates)
    return BatchUpdateOffsetsResponse(
        success=len(errors) == 0,
        updated_count=updated_count,
        errors=errors,
    )

"""
Layer: Interface Adapters — Controller (Web)
Package: web.routers.data_extraction.relations
Responsibility: HTTP route handlers для связей между аннотациями.

Allowed imports: fastapi, application.relations.*, web.dependencies, src.schemas.api
Forbidden imports: neomodel (напрямую), services (напрямую)
"""
from typing import Dict, Any

from fastapi import APIRouter, Depends

from src.schemas.api import CreateRelationRequest
from application.relations.create_annotation_relation import create_annotation_relation
from application.relations.delete_annotation_relation import delete_annotation_relation
from application.relations.get_annotation_relations import get_annotation_relations
from web.dependencies import get_annotation_repository, get_document_repository, get_current_user

router = APIRouter(tags=["relations"])


@router.post("/annotations/{source_id}/relations", response_model=Dict[str, Any])
async def create_relation_route(
    source_id: str,
    request: CreateRelationRequest,
    ann_repo=Depends(get_annotation_repository),
    _user: dict = Depends(get_current_user),
):
    rel = create_annotation_relation(
        repo=ann_repo,
        source_id=source_id,
        target_id=request.target_id,
        relation_type=request.relation_type,
        metadata=request.metadata,
    )
    return {
        "success": True,
        "relation": {
            "relation_uid": rel.uid,
            "source_uid": rel.source_uid,
            "target_uid": rel.target_uid,
            "relation_type": rel.relation_type,
            "created_date": str(rel.created_date) if rel.created_date else None,
            "metadata": rel.metadata or {},
        },
    }


@router.delete("/annotations/{source_id}/relations/{target_id}", response_model=Dict[str, Any])
async def delete_relation_route(
    source_id: str,
    target_id: str,
    ann_repo=Depends(get_annotation_repository),
    _user: dict = Depends(get_current_user),
):
    delete_annotation_relation(repo=ann_repo, source_id=source_id, target_id=target_id)
    return {"success": True, "message": "Relation deleted"}


@router.get("/documents/{doc_id}/relations", response_model=Dict[str, Any])
async def get_relations_route(
    doc_id: str,
    ann_repo=Depends(get_annotation_repository),
    doc_repo=Depends(get_document_repository),
):
    relations = get_annotation_relations(
        annotation_repo=ann_repo, document_repo=doc_repo, doc_id=doc_id
    )
    return {
        "success": True,
        "relations": [
            {
                "relation_uid": r.uid,
                "source_uid": r.source_uid,
                "target_uid": r.target_uid,
                "relation_type": r.relation_type,
                "created_date": str(r.created_date) if r.created_date else None,
                "metadata": r.metadata or {},
            }
            for r in relations
        ],
    }

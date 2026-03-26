"""
Layer: Interface Adapters — Controller (Web)
Package: web.routers.data_extraction.actions
Responsibility: HTTP route handlers для извлечения действий и human-in-the-loop ревью.

Allowed imports: fastapi, application.actions.*, web.dependencies, src.schemas.api
Forbidden imports: neomodel (напрямую), infrastructure (напрямую)
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException

from src.schemas.api import (
    ExtractActionsResponse,
    PendingEdge,
    PendingEdgesResponse,
    ReviewEdgeRequest,
    ConfirmedActionNode,
    ConfirmedActionEdge,
    ConfirmedActionGraphResponse,
)
from application.actions.extract_document_actions import (
    extract_document_actions,
    review_action_edge,
)
from web.dependencies import (
    get_document_repository,
    get_action_repository,
    get_nlp_client_dep,
    get_s3,
)
from domain.exceptions import NotFoundError, ConflictError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents/{doc_id}", tags=["actions"])


@router.post("/extract-actions", response_model=ExtractActionsResponse)
async def extract_actions(
    doc_id: str,
    clear_existing: bool = Query(default=False),
    document_repo=Depends(get_document_repository),
    action_repo=Depends(get_action_repository),
    nlp_client=Depends(get_nlp_client_dep),
    storage=Depends(get_s3),
):
    try:
        result = await extract_document_actions(
            doc_id=doc_id,
            document_repo=document_repo,
            action_repo=action_repo,
            nlp_client=nlp_client,
            storage=storage,
            clear_existing=clear_existing,
        )
        return ExtractActionsResponse(
            success=True,
            doc_id=doc_id,
            actions_count=result.actions_count,
            edges_count=result.edges_count,
            pending_count=result.pending_count,
            message=f"Extracted {result.actions_count} actions, {result.pending_count} pending edges",
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Error extracting actions for doc %s", doc_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/actions/pending", response_model=PendingEdgesResponse)
def get_pending_edges(
    doc_id: str,
    action_repo=Depends(get_action_repository),
):
    rows = action_repo.get_pending_for_document(doc_id)
    edges = [
        PendingEdge(
            src_uid=row["src_uid"],
            src_text=row["src_text"] or "",
            src_phrase=row["src_phrase"] or "",
            src_sentence=row["src_sentence"] or "",
            src_class=row["src_class"] or "action",
            tgt_uid=row["tgt_uid"],
            tgt_text=row["tgt_text"] or "",
            tgt_phrase=row["tgt_phrase"] or "",
            tgt_sentence=row["tgt_sentence"] or "",
            tgt_class=row["tgt_class"] or "action",
            relation_subtype=row["relation_subtype"] or "",
            confidence=row["confidence"] or 0.0,
            evidence=row["evidence"] or [],
        )
        for row in rows
    ]
    return PendingEdgesResponse(
        success=True,
        doc_id=doc_id,
        edges=edges,
        total=len(edges),
    )


@router.post("/actions/review")
def review_edge(
    doc_id: str,
    body: ReviewEdgeRequest,
    action_repo=Depends(get_action_repository),
):
    try:
        review_action_edge(
            doc_id=doc_id,
            src_uid=body.src_uid,
            tgt_uid=body.tgt_uid,
            relation_subtype=body.relation_subtype,
            decision=body.decision,
            action_repo=action_repo,
        )
        return {"success": True}
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        logger.exception("Error reviewing edge for doc %s", doc_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/actions")
def delete_actions(
    doc_id: str,
    action_repo=Depends(get_action_repository),
):
    count = action_repo.delete_for_document(doc_id)
    return {"success": True, "deleted": count}


@router.get("/actions/graph", response_model=ConfirmedActionGraphResponse)
def get_confirmed_graph(
    doc_id: str,
    action_repo=Depends(get_action_repository),
):
    nodes_data, edges_data = action_repo.get_confirmed_graph(doc_id)
    nodes = [ConfirmedActionNode(**n) for n in nodes_data]
    edges = [ConfirmedActionEdge(**e) for e in edges_data]
    return ConfirmedActionGraphResponse(
        success=True,
        doc_id=doc_id,
        nodes=nodes,
        edges=edges,
        total_nodes=len(nodes),
        total_edges=len(edges),
    )

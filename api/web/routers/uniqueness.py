"""
Layer: Frameworks & Drivers — Web
Router: /api/uniqueness/*
Responsibility: REST endpoints для проверки уникальности знаний.

Algorithms used:
- Level 1: fingerprint + cosine vector search (single statement)
- Level 2: WL-hash + VF2 + gSpan/Gaston/FSG (connected subgraph)
- Level 3: typed VF2 subgraph isomorphism (pattern from UI)
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from web.dependencies import get_current_user, get_optional_user
from services.knowledge_language_grpc_client import get_kl_grpc_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/uniqueness", tags=["uniqueness"])


# ── Request / Response Models ─────────────────────────────────────────────────


class StatementInput(BaseModel):
    subject_text: str = Field(..., description="Текст субъекта утверждения")
    predicate: str = Field(..., description="Предикат (тип связи)")
    object_text: str = Field(..., description="Текст объекта утверждения")
    sentence_text: str = Field(..., description="Полное предложение/текст утверждения")


class AddStatementInput(StatementInput):
    doc_id: str = Field(default="", description="ID документа-источника")


class SubgraphNodeInput(BaseModel):
    id: str
    node_type: str = "concept"
    text: str = ""
    predicate: str = ""
    fingerprint: str = ""


class SubgraphEdgeInput(BaseModel):
    source_id: str
    target_id: str
    edge_type: str = "RELATES_TO"
    predicate: str = ""


class SubgraphInput(BaseModel):
    nodes: list[SubgraphNodeInput]
    edges: list[SubgraphEdgeInput]


class PatternNodeInput(BaseModel):
    id: str
    required_type: str = ""
    text_constraint: str = ""
    predicate_constraint: str = ""


class PatternEdgeInput(BaseModel):
    source_id: str
    target_id: str
    required_edge_type: str = ""
    predicate_constraint: str = ""


class PatternInput(BaseModel):
    nodes: list[PatternNodeInput]
    edges: list[PatternEdgeInput]
    max_results: int = 100


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/check")
async def check_uniqueness(
    statement: StatementInput,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Проверяет уникальность одного утверждения.

    Алгоритм:
    1. SHA256 fingerprint (canonical form) → O(1) lookup
    2. Sentence embedding + Qdrant search → O(log N)
    3. Cosine similarity threshold → SAME / UNCERTAIN / DIFFERENT / NEW
    """
    from application.uniqueness.check_uniqueness import check_knowledge_uniqueness

    result = await check_knowledge_uniqueness(
        grpc_client=get_kl_grpc_client(),
        subject_text=statement.subject_text,
        predicate=statement.predicate,
        object_text=statement.object_text,
        sentence_text=statement.sentence_text,
    )

    return {
        "success": result.get("status") != "UNKNOWN",
        **result,
    }


@router.post("/add")
async def add_with_uniqueness(
    statement: AddStatementInput,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Добавляет утверждение с проверкой уникальности.

    Если status=SAME → создаёт ссылку нового источника на существующее утверждение.
    Если status=NEW  → создаёт новое утверждение в графе.
    Если status=UNCERTAIN → помечает для ревью.
    """
    from application.uniqueness.add_knowledge import add_knowledge_with_uniqueness

    result = await add_knowledge_with_uniqueness(
        grpc_client=get_kl_grpc_client(),
        subject_text=statement.subject_text,
        predicate=statement.predicate,
        object_text=statement.object_text,
        sentence_text=statement.sentence_text,
        doc_id=statement.doc_id,
    )

    return {
        "success": result.get("success", False),
        **result,
    }


@router.post("/check-subgraph")
async def check_subgraph(
    subgraph: SubgraphInput,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Проверяет уникальность подграфа из связанных утверждений.

    Алгоритм:
    1. WL-hash подграфа → O(|V|·|E|) lookup
    2. VF2 subgraph isomorphism → O(|V|!·|V'|!) worst, O(|V|·|V'|·deg²) practical
    3. gSpan/Gaston/FSG frequent mining → O(2^|V|) worst, O(|V|·|E|) practical
    """
    from application.uniqueness.check_subgraph import check_subgraph_uniqueness

    nodes = [n.model_dump() for n in subgraph.nodes]
    edges = [e.model_dump() for e in subgraph.edges]

    result = await check_subgraph_uniqueness(
        grpc_client=get_kl_grpc_client(),
        nodes=nodes,
        edges=edges,
    )

    return {
        "success": result.get("status") != "UNKNOWN",
        **result,
    }


@router.post("/check-pattern")
async def check_pattern(
    pattern: PatternInput,
    user: Optional[dict] = Depends(get_optional_user),
) -> dict[str, Any]:
    """
    Проверяет паттерн из UI редактора на графе утверждений.

    Алгоритм: Typed VF2 subgraph isomorphism с ограничениями по типам узлов/рёбер.
    """
    from application.uniqueness.check_subgraph import check_pattern_match

    nodes = [n.model_dump() for n in pattern.nodes]
    edges = [e.model_dump() for e in pattern.edges]

    result = await check_pattern_match(
        grpc_client=get_kl_grpc_client(),
        nodes=nodes,
        edges=edges,
        max_results=pattern.max_results,
    )

    return {
        "success": result.get("status") != "UNKNOWN",
        **result,
    }

"""
REST endpoints для лингвистического графа (Action + LexicalUnit).

Endpoints:
  GET  /api/patterns/linguistic-graph/{doc_id}       — граф одного документа
  GET  /api/patterns/global-linguistic-graph         — глобальный граф всех документов
  POST /api/patterns/global-linguistic-graph/layout  — вычислить и сохранить layout
"""
from typing import Dict, Any, List
import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from adapters.repositories.pattern_graph_repository import PatternGraphRepository
from application.patterns.graph_layout import compute_and_save_layout
from web.dependencies import get_pattern_graph_repository

router = APIRouter(prefix="/api/patterns", tags=["patterns"])
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Linguistic graph endpoints
# ---------------------------------------------------------------------------


@router.get("/linguistic-graph/{doc_id}")
def get_document_linguistic_graph(
    doc_id: str,
    repo: PatternGraphRepository = Depends(get_pattern_graph_repository),
) -> Dict[str, Any]:
    """Возвращает лингвистический граф одного документа.

    Nodes: Action и LexicalUnit.
    Edges: LEADS_TO, DEPENDS_ON, PART_OF.
    """
    try:
        nodes, edges = repo.get_document_linguistic_graph(doc_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка получения графа: {e}")

    return {"doc_id": doc_id, "nodes": nodes, "edges": edges}


@router.get("/global-linguistic-graph")
async def get_global_linguistic_graph(
    lexical_limit: int = Query(1000, ge=100, le=10000, description="Лимит LexicalUnit нод"),
    action_limit: int = Query(3000, ge=100, le=10000, description="Лимит Action нод"),
    edge_limit: int = Query(3000, ge=100, le=10000, description="Лимит рёбер на тип"),
    auto_layout: bool = Query(True, description="Автоматически вычислять layout если нет координат"),
    repo: PatternGraphRepository = Depends(get_pattern_graph_repository),
) -> Dict[str, Any]:
    """Возвращает объединённый лингвистический граф всех документов.

    Actions ограничены action_limit (топ по doc_count).
    LexicalUnit ограничены lexical_limit (топ по частоте).
    Рёбра DEPENDS_ON/PART_OF/LEADS_TO ограничены edge_limit каждый.
    Автоматически вычисляет layout если координаты отсутствуют.
    """
    try:
        nodes, edges = repo.get_global_linguistic_graph(
            lexical_limit=lexical_limit,
            action_limit=action_limit,
            edge_limit=edge_limit,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка получения графа: {e}")

    # Проверяем наличие layout координат
    has_layout = any(n.get("layout_x") is not None and n.get("layout_y") is not None for n in nodes)
    
    # Автоматически вычисляем layout если нужно
    if auto_layout and not has_layout and nodes:
        try:
            # Используем больше итераций для качественного layout
            iterations = 300 if len(nodes) < 2000 else 500
            compute_and_save_layout(nodes, edges, iterations=iterations, save_to_db=True)
            # Перезагружаем граф с новыми координатами
            nodes, edges = repo.get_global_linguistic_graph(
                lexical_limit=lexical_limit,
                action_limit=action_limit,
                edge_limit=edge_limit,
            )
        except Exception as e:
            logger.warning(f"Не удалось вычислить layout: {e}")

    return {"nodes": nodes, "edges": edges}


@router.post("/global-linguistic-graph/layout")
def compute_global_layout(
    iterations: int = 50,
    repo: PatternGraphRepository = Depends(get_pattern_graph_repository),
) -> Dict[str, Any]:
    """Вычисляет force-directed layout на сервере и сохраняет координаты в Neo4j."""
    try:
        nodes, edges = repo.get_global_linguistic_graph()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка получения графа: {e}")

    if not nodes:
        return {"status": "empty", "message": "Граф пуст"}

    positions = compute_and_save_layout(nodes, edges, iterations=iterations, save_to_db=True)

    return {
        "status": "ok",
        "nodes_computed": len(positions),
        "message": f"Layout вычислен для {len(positions)} узлов",
    }

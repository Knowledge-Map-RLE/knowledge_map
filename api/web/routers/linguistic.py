"""
REST endpoints для анализа лингвистических паттернов в графе знаний.
"""
from typing import Optional, List

from fastapi import APIRouter, Depends, Query

from application.ports.repositories import ActionRepositoryProtocol
from web.dependencies import get_action_repository

router = APIRouter(prefix="/api/linguistic", tags=["linguistic"])


@router.get("/search")
def search_lexical_units(
    lemma: Optional[str] = Query(None, description="Лемма для поиска"),
    pos: Optional[str] = Query(None, description="Часть речи (NOUN, VERB, ADJ, ...)"),
    dep: Optional[str] = Query(None, description="Dependency label (nsubj, dobj, amod, ...)"),
    doc_id: Optional[str] = Query(None, description="ID документа"),
    limit: int = Query(100, ge=1, le=1000),
    repo: ActionRepositoryProtocol = Depends(get_action_repository),
):
    """Поиск LexicalUnit по атрибутам."""
    results = repo.search_lexical_units(
        lemma=lemma, pos=pos, dep=dep, doc_id=doc_id, limit=limit
    )
    return {"count": len(results), "results": results}


@router.get("/dependency-patterns")
def dependency_patterns(
    doc_id: Optional[str] = Query(None, description="ID документа (опционально)"),
    repo: ActionRepositoryProtocol = Depends(get_action_repository),
):
    """Частотные синтаксические паттерны (head→dependent через DEPENDS_ON)."""
    patterns = repo.find_dependency_patterns(doc_id=doc_id)
    return {"count": len(patterns), "patterns": patterns}


@router.get("/shared-patterns")
def shared_patterns(
    min_docs: int = Query(2, ge=2, le=50, description="Минимальное кол-во документов"),
    repo: ActionRepositoryProtocol = Depends(get_action_repository),
):
    """Паттерны, повторяющиеся в разных документах."""
    patterns = repo.find_shared_patterns(min_docs=min_docs)
    return {"count": len(patterns), "patterns": patterns}


@router.get("/stats")
def lexical_stats(
    repo: ActionRepositoryProtocol = Depends(get_action_repository),
):
    """Статистика лингвистического графа."""
    stats = repo.get_lexical_graph_stats()
    return stats


@router.get("/compare-actions/{uid1}/{uid2}")
def compare_actions(
    uid1: str,
    uid2: str,
    repo: ActionRepositoryProtocol = Depends(get_action_repository),
):
    """Сравнение лингвистической структуры двух Actions."""
    result = repo.compare_actions(uid1, uid2)
    return result

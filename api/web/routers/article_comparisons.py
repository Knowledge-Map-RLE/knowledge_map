"""API сравнения конкретных запусков с проверкой владельца каждой статьи."""
import asyncio
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from application.compare_article_maps import CompareArticleMaps
from domain.article_maps import ArticleMapError, ArticleMapNotFound
from infrastructure.article_comparison_controls import FixedComparisonControls
from infrastructure.neo4j.article_comparisons_repository import Neo4jArticleComparisonsRepository
from web.dependencies import get_current_user
from web.routers.article_maps import repository, http_error

router = APIRouter(prefix="/article_editor/comparisons", tags=["article_comparisons"])


class MapReference(BaseModel):
    article_id: str
    pipeline_id: Literal["text_reified"]
    run_id: str

    model_config = ConfigDict(extra="forbid")


class ComparisonRequest(BaseModel):
    target: MapReference
    sources: list[MapReference]

    model_config = ConfigDict(extra="forbid")


@router.post("")
async def create_comparison(body: ComparisonRequest, user=Depends(get_current_user), maps=Depends(repository)):
    try:
        ref = lambda r: r.model_dump() if hasattr(r, "model_dump") else r.dict()
        return await asyncio.to_thread(CompareArticleMaps(maps, Neo4jArticleComparisonsRepository(maps), FixedComparisonControls()).execute,
                                       ref(body.target), [ref(s) for s in body.sources], user["uid"])
    except ArticleMapError as exc:
        raise http_error(exc) from exc


@router.get("")
async def list_comparisons(article_id: str | None = None, user=Depends(get_current_user), maps=Depends(repository)):
    try:
        return {"comparisons": await asyncio.to_thread(Neo4jArticleComparisonsRepository(maps).list, user["uid"], article_id)}
    except ArticleMapError as exc:
        raise http_error(exc) from exc


@router.get("/runs")
async def list_runs(offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=200),
                    user=Depends(get_current_user), maps=Depends(repository)):
    try:
        return await asyncio.to_thread(Neo4jArticleComparisonsRepository(maps).runs, user["uid"], offset, limit)
    except ArticleMapError as exc:
        raise http_error(exc) from exc


@router.get("/{comparison_id}")
async def get_comparison(comparison_id: str, user=Depends(get_current_user), maps=Depends(repository)):
    try:
        result = await asyncio.to_thread(Neo4jArticleComparisonsRepository(maps).get, comparison_id, user["uid"])
        if result is None:
            raise ArticleMapNotFound("Comparison not found")
        return result
    except ArticleMapError as exc:
        raise http_error(exc) from exc


@router.get("/{comparison_id}/pairs")
async def get_pairs(comparison_id: str, mode: Literal["text", "semantic", "hybrid"] = "hybrid", left_knowledge_id: str | None = None,
                    source_article_id: str | None = None, right_knowledge_id: str | None = None, relation: str | None = None, offset: int = Query(0, ge=0),
                    limit: int = Query(10, ge=1, le=100), user=Depends(get_current_user), maps=Depends(repository)):
    try:
        return await asyncio.to_thread(Neo4jArticleComparisonsRepository(maps).pairs, comparison_id, user["uid"], mode=mode,
            left_knowledge_id=left_knowledge_id, source_article_id=source_article_id, right_knowledge_id=right_knowledge_id,
            relation=relation, offset=offset, limit=limit)
    except ArticleMapError as exc:
        raise http_error(exc) from exc

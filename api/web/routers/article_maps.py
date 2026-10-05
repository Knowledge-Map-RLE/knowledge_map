"""API двух независимых карт статьи: построение, просмотр и перевод."""
from __future__ import annotations

import asyncio
import copy
import json
import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from application.rebuild_article_map import RebuildArticleMap
from application.text_to_map import TextToMap, TranslateArticleMap
from domain.article_maps import (
    ArticleMapError, ArticleMapAccessDenied, ArticleMapNotFound, ArticleMapBusy, ArticleMapConflict, digest,
)
from domain.knowledge_map_schema import extraction_map_json_schema
from infrastructure.article_map_model import ArticleMapDependencyModelGateway, ArticleMapModelGateway
from infrastructure.article_map_source import StoredArticleMapSource
from infrastructure.config import settings
from infrastructure.neo4j.article_pipeline_repository import Neo4jArticlePipelineRepository
from infrastructure.neo4j.article_maps_repository import Neo4jArticleMapsRepository
from infrastructure.s3.s3_storage import get_s3_client
from services.article_editor_service import ArticleEditorService
from web.dependencies import get_current_user
from knowledge_contracts.validation import ValidationError

router = APIRouter(prefix="/article_editor/articles/{doc_id}/maps", tags=["article_maps"])
PipelineId = Literal["text_reified", "structural_rows"]
log = logging.getLogger(__name__)


def make_repository():
    return Neo4jArticleMapsRepository(settings.NEO4J_URI, settings.NEO4J_USER, settings.NEO4J_PASSWORD,
                                    lease_seconds=2 * settings.LLM_TIMEOUT + 300)


def repository():
    repo = make_repository()
    try:
        yield repo
    finally:
        repo.close()


def source_reader(repo):
    return StoredArticleMapSource(repo, get_s3_client(), settings.S3_BUCKET_NAME)


def http_error(exc):
    status = 403 if isinstance(exc, ArticleMapAccessDenied) else 404 if isinstance(exc, ArticleMapNotFound) else (
        409 if isinstance(exc, (ArticleMapBusy, ArticleMapConflict)) else 422)
    return HTTPException(status, detail=str(exc))


@router.on_event("startup")
async def initialize_article_maps():
    repo = make_repository()
    try:
        await asyncio.to_thread(repo.ensure_schema)
        await asyncio.to_thread(repo.migrate_legacy_snapshots)
    finally:
        repo.close()


@router.get("")
async def list_maps(doc_id: str, user=Depends(get_current_user), repo=Depends(repository)):
    try:
        maps = await asyncio.to_thread(repo.list_maps, doc_id, user["uid"])
        stored = await ArticleEditorService().get_blocks(doc_id)
        # Отсутствие текста — состояние доступности кнопки; ошибки сети не маскируются.
        text_available = await source_reader(repo).available(doc_id, user["uid"])
        return {"maps": maps, "availability": {"text_reified": text_available,
                                                "structural_rows": bool(stored.get("blocks"))}}
    except ArticleMapError as exc:
        raise http_error(exc) from exc


@router.get("/{pipeline_id}")
async def get_map(doc_id: str, pipeline_id: PipelineId, locale: Literal["en", "ru"] = "en",
                  user=Depends(get_current_user), repo=Depends(repository)):
    try:
        result = await asyncio.to_thread(repo.get, doc_id, pipeline_id, user["uid"])
        if result is None:
            raise ArticleMapNotFound("Map has not been built")
        result["locale"] = locale
        if locale == "ru":
            translation = result.get("translations", {}).get("ru")
            if not translation or translation["run_id"] != result["run_id"]:
                raise ArticleMapConflict("Russian translation has not been created for this map")
            result = copy.deepcopy(result)
            for node in result["graph"]["nodes"]:
                node["display_text"] = translation["labels"][node["id"]]
        result.pop("translations", None)
        result.pop("source", None)
        return result
    except ArticleMapError as exc:
        raise http_error(exc) from exc


@router.get("/{pipeline_id}/provenance/{node_id}")
async def provenance(doc_id: str, pipeline_id: PipelineId, node_id: str,
                     user=Depends(get_current_user), repo=Depends(repository)):
    try:
        result = await asyncio.to_thread(repo.get, doc_id, pipeline_id, user["uid"])
        if not result or "source" not in result:
            raise ArticleMapNotFound("Source provenance is unavailable for this map")
        node = next((n for n in result["graph"]["nodes"] if n["id"] == node_id), None)
        if node is None:
            raise ArticleMapNotFound("Map node not found")
        source = result["source"]
        return {"node": node, "source_sha256": source["sha256"], "offset_encoding": source["offset_encoding"],
                "fragments": [{**span, "text": source["text"][span["start"]:span["end"]]}
                              for span in node["provenance"]["source_spans"]]}
    except ArticleMapError as exc:
        raise http_error(exc) from exc


@router.post("/structural_rows/build")
async def build_from_rows(doc_id: str, user=Depends(get_current_user), repo=Depends(repository)):
    legacy = Neo4jArticlePipelineRepository(settings.NEO4J_URI, settings.NEO4J_USER, settings.NEO4J_PASSWORD)
    try:
        await asyncio.to_thread(repo.authorize, doc_id, user["uid"])
        blocks = (await ArticleEditorService().get_blocks(doc_id)).get("blocks", [])
        return await RebuildArticleMap(legacy, repo).execute_current(doc_id, user["uid"], blocks)
    except ArticleMapError as exc:
        raise http_error(exc) from exc
    except ValidationError as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    finally:
        legacy.close()


async def authorize_stream(repo, doc_id, user_uid):
    try:
        await asyncio.to_thread(repo.authorize, doc_id, user_uid)
    except BaseException as exc:
        repo.close()
        if isinstance(exc, ArticleMapError):
            raise http_error(exc) from exc
        raise


@router.post("/{pipeline_id}/translate")
async def translate(doc_id: str, pipeline_id: PipelineId, user=Depends(get_current_user)):
    repo = make_repository()
    await authorize_stream(repo, doc_id, user["uid"])
    async def action(emit):
        await emit({"type": "progress", "stage": "translation"})
        return await TranslateArticleMap(repo, ArticleMapModelGateway()).execute(doc_id, pipeline_id, user["uid"])
    return stream_operation(repo, doc_id, action)


@router.post("/text_reified/build")
async def build_from_text(doc_id: str, user=Depends(get_current_user)):
    repo = make_repository()
    await authorize_stream(repo, doc_id, user["uid"])
    async def action(emit):
        model = ArticleMapModelGateway(output_schema=extraction_map_json_schema(), strict_schema=True)
        dependencies = ArticleMapDependencyModelGateway()
        return await TextToMap(repo, source_reader(repo), model, dependencies).execute(doc_id, user["uid"], emit)
    return stream_operation(repo, doc_id, action)


def stream_operation(repo, doc_id, action):
    """Единый SSE-транспорт долгих операций с отменой и освобождением ресурсов."""

    async def stream():
        queue = asyncio.Queue()
        async def emit(event):
            await queue.put(event)
        async def run():
            try:
                result = await action(emit)
                result.pop("source", None)
                await emit({"type": "result", "data": result})
            except asyncio.CancelledError:
                await emit({"type": "cancelled"})
                raise
            except ArticleMapError as exc:
                await emit({"type": "error", "message": str(exc)})
            except Exception as exc:
                log.error("article_map build failed article=%s reason=%s", doc_id, type(exc).__name__)
                await emit({"type": "error", "message": "Article map conversion failed"})
            finally:
                await queue.put(None)
        task = asyncio.create_task(run())
        try:
            yield "data: " + json.dumps({"type": "start", "total": 1}) + "\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    # Комментарий SSE не даёт proxy закрыть длинный LLM-запрос по idle timeout.
                    yield ": keep-alive\n\n"
                    continue
                if event is None:
                    break
                yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
            yield "data: [DONE]\n\n"
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            repo.close()
    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

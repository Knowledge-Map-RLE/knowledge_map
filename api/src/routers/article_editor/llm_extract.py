"""Authenticated, versioned article extraction and provenance endpoints."""
from __future__ import annotations
import asyncio
import json
from itertools import chain
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from web.dependencies import get_current_user
from infrastructure.config import resolve_model_profile, settings
from infrastructure.article_pipeline import LinguisticGateway, SemanticGateway
from infrastructure.neo4j.article_pipeline_repository import Neo4jArticlePipelineRepository
from application.article_pipeline import ExtractArticle
from knowledge_contracts.validation import ValidationError
from knowledge_pipeline.pipeline import checksum
from services.article_editor_service import ArticleEditorService

router = APIRouter(tags=["article_editor"])
service = ArticleEditorService()

class LlmExtractRequest(BaseModel):
    text: str = ""
    doc_id: str = ""
    model: str = resolve_model_profile("article_extraction")
    save: bool = True

def repository():
    repo = Neo4jArticlePipelineRepository(settings.NEO4J_URI,settings.NEO4J_USER,settings.NEO4J_PASSWORD)
    try:
        yield repo
    finally:
        repo.close()

def authorize(repo,doc_id,user):
    try:
        repo.authorize(doc_id,user["uid"])
    except ValidationError as exc:
        raise HTTPException(403,detail=str(exc)) from exc

def event(data):
    return "data: " + json.dumps(data,ensure_ascii=False) + "\n\n"

@router.post("/article_editor/articles/{doc_id}/llm-extract")
async def extract(doc_id: str, req: LlmExtractRequest, user=Depends(get_current_user)):
    # Repository lifetime must cover the whole streaming response.
    repo = Neo4jArticlePipelineRepository(settings.NEO4J_URI,settings.NEO4J_USER,settings.NEO4J_PASSWORD)
    try:
        authorize(repo,doc_id,user)
        if req.doc_id and req.doc_id != doc_id:
            raise HTTPException(422,detail="Article identifiers differ")
        if req.model != resolve_model_profile("article_extraction"):
            raise HTTPException(
                422,
                detail=f"Required model profile: {resolve_model_profile('article_extraction')}",
            )
        text = req.text
        if not text.strip():
            text = (await service.get_article_text(doc_id)).get("text","")
        if not text.strip():
            raise HTTPException(422,detail="Full article text is required")
        if req.save:
            await asyncio.to_thread(repo.ensure_indexes)
    except Exception:
        repo.close()
        raise
    async def stream():
        queue = asyncio.Queue()
        async def emit(data):
            await queue.put(data)
        async def run():
            try:
                result = await ExtractArticle(repo,LinguisticGateway(),SemanticGateway(req.model)).execute(
                    doc_id,text,user["uid"],emit,req.save)
                if not result.get("success"):
                    await emit({"type":"error","message":result.get("error") or "Extraction failed"})
                else:
                    await emit({"type":"result","data":{
                        "success":True,"version_id":result["version_id"],"run_id":result["run_id"],
                        "status":result["status"],"coverage":result["coverage"],
                        "timing":result.get("timing",{}),
                        "quality_metrics":result.get("quality_metrics",{}),
                        "summary":{"blocks":len(result["blocks"]),
                                   "relations":sum(b["blockType"] in ("relation","temporal_relation") for b in result["blocks"])},
                        "saved":req.save,"blocks":result["blocks"] if not req.save else []}})
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                await emit({"type":"error","message":str(exc)})
            finally:
                await queue.put(None)
        task = asyncio.create_task(run())
        try:
            yield event({"type":"start","total":1})
            while True:
                message = await queue.get()
                if message is None:
                    break
                yield event(message)
            yield "data: [DONE]\n\n"
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task,return_exceptions=True)
            repo.close()
    return StreamingResponse(stream(),media_type="text/event-stream",headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})

@router.get("/article_editor/articles/{doc_id}/pipeline/versions")
def versions(doc_id: str,user=Depends(get_current_user),repo=Depends(repository)):
    authorize(repo,doc_id,user)
    return {"versions":repo.versions(doc_id,user["uid"])}

@router.get("/article_editor/articles/{doc_id}/pipeline/versions/{version_id}")
def version(doc_id: str,version_id: str,user=Depends(get_current_user),repo=Depends(repository)):
    authorize(repo,doc_id,user)
    try:
        result=repo.load(doc_id,version_id,user["uid"])
    except ValidationError as exc:
        raise HTTPException(404,detail=str(exc)) from exc
    return {k:result.get(k) for k in ("version_id","run_id","stage","status","processed","total",
        "error","coverage","validation","quality_metrics","graph","timing","model_steps")} | {"issues":result.get("validation",{}).get("issues",[])}

@router.get("/article_editor/articles/{doc_id}/pipeline/versions/{version_id}/provenance/{entity_id}")
def provenance(doc_id: str,version_id: str,entity_id: str,user=Depends(get_current_user),repo=Depends(repository)):
    authorize(repo,doc_id,user)
    result=repo.load(doc_id,version_id,user["uid"])
    block=next((b for b in result.get("blocks",[]) if b["instanceId"]==entity_id),None)
    if block is None:
        raise HTTPException(404,detail="Entity not found")
    spans=block["data"]["provenance"]["source_spans"]
    fragment = result["source"]["text"][spans[0]["start"]:spans[0]["end"]] if spans else ""
    token_ids=set(chain.from_iterable(t["token_ids"] for t in result["linguistic_profile"]["sentences"]
                                      if any(s["start"] < t["end"] and s["end"] > t["start"]
                                             for s in spans)))
    return {"article_id":doc_id,"source":result["source"],"structural":block,
        "fragment":fragment,
        "tokens":[t for t in result["linguistic_profile"]["tokens"] if t["id"] in token_ids]}

@router.post("/article_editor/articles/{doc_id}/pipeline/versions/{version_id}/apply")
async def apply_version(doc_id: str,version_id: str,user=Depends(get_current_user),repo=Depends(repository)):
    authorize(repo,doc_id,user)
    current=await service.get_article_text(doc_id)
    try:
        await asyncio.to_thread(repo.apply,doc_id,version_id,user["uid"],checksum(current.get("text","")))
    except ValidationError as exc:
        raise HTTPException(409,detail=str(exc)) from exc
    from services.knowledge_triples_service import invalidate_knowledge_triples_cache
    invalidate_knowledge_triples_cache()
    return {"success":True,"version_id":version_id}

@router.get("/article_editor/articles/{doc_id}/pipeline/versions/{version_id}/stages/{stage}")
def stage_result(doc_id: str, version_id: str, stage: str, user=Depends(get_current_user), repo=Depends(repository)):
    authorize(repo, doc_id, user)
    fields = {"source":"source", "linguistic":"linguistic_profile",
              "linguistic_profile":"linguistic_profile", "structural":"blocks", "map":"graph",
              "model":"model_steps"}
    if stage not in fields:
        raise HTTPException(422, detail="Unknown pipeline stage")
    try:
        result = repo.load(doc_id, version_id, user["uid"])
    except ValidationError as exc:
        raise HTTPException(404, detail=str(exc)) from exc
    value = result.get(fields[stage])
    if value is None:
        raise HTTPException(409, detail="Stage has not completed")
    return {"run_id":result["run_id"], "version_id":version_id, "stage":stage, "result":value}

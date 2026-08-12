import asyncio
import json
import logging
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from services.knowledge_language_grpc_client import get_kl_grpc_client
from services.article_editor_service import ArticleEditorService
from web.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["article_editor"])


def _background_save(coro):
    """Fire-and-forget with error logging."""
    task = asyncio.ensure_future(coro)
    task.add_done_callback(lambda t: logger.error("Background save failed: %s", t.exception()) if t.exception() else None)


service = ArticleEditorService()


class ParseRequest(BaseModel):
    text: str
    doc_id: str = ""
    use_llm: bool = False
    save: bool = False


@router.post("/article_editor/parse")
async def parse_text(req: ParseRequest, user: dict = Depends(get_current_user)):
    client = get_kl_grpc_client()
    result = await client.process_text(text=req.text, doc_id=req.doc_id, timeout=600)
    if not result.get("success"):
        logger.warning("Parse failed: %s", result.get("message", ""))
        return {"success": False, "statements": [], "concepts": [], "total_statements": 0, "total_concepts": 0, "message": result.get("message", "Parsing failed"), "doc_id": req.doc_id}
    # Save in background (sync Neo4j is slow for many statements)
    if req.save and req.doc_id:
        _background_save(service.save_statements(req.doc_id, result.get("statements", []), user_uid=user["uid"]))
        _background_save(service.save_article_text(req.doc_id, req.text))
    return result


@router.post("/article_editor/parse_stream")
async def parse_text_stream(req: ParseRequest, user: dict = Depends(get_current_user)):
    client = get_kl_grpc_client()

    async def event_generator():
        yield f"data: {json.dumps({'type': 'start', 'total': 1})}\n\n"

        result = await client.process_text(text=req.text, doc_id=req.doc_id, timeout=600)

        if not result.get("success"):
            yield f"data: {json.dumps({'type': 'result', 'data': result})}\n\n"
            yield "data: [DONE]\n\n"
            return

        # Send result to client immediately, before save (save is slow, sync Neo4j)
        yield f"data: {json.dumps({'type': 'result', 'data': result})}\n\n"
        yield "data: [DONE]\n\n"

        # Save in background — fire-and-forget
        if req.save and req.doc_id:
            _background_save(service.save_statements(req.doc_id, result.get("statements", []), user_uid=user["uid"]))
            _background_save(service.save_article_text(req.doc_id, req.text))

    return StreamingResponse(event_generator(), media_type="text/event-stream")

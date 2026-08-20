import asyncio
import json
import logging
import queue
import threading
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from services.article_editor_service import ArticleEditorService
from services.llm_triplet_extraction_service import (
    LLMTripletExtractionService,
    DEFAULT_MODEL,
)
from web.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["article_editor"])

service = ArticleEditorService()


class LlmExtractRequest(BaseModel):
    text: str = ""
    doc_id: str = ""
    model: str = DEFAULT_MODEL
    save: bool = True


def _event(data: Dict[str, Any]) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


@router.post("/article_editor/articles/{doc_id}/llm-extract")
async def llm_extract_blocks(
    doc_id: str, req: LlmExtractRequest, user: dict = Depends(get_current_user)
):
    """Извлекает структурные блоки из текста статьи через LLM (SSE-поток).

    Unified one-stage извлечение: вся статья за один LLM-вызов.

    События:
        {type: "start", total: 1}
        {type: "result", data: {success, blocks, summary, chunks}}
        {type: "error", message}
        {type: "cancelled"}
        data: [DONE]
    """
    text = (req.text or "").strip()
    if not text:
        return StreamingResponse(
            iter([
                _event({"type": "error", "message": "Текст статьи пуст"}),
                "data: [DONE]\n\n",
            ]),
            media_type="text/event-stream",
        )

    article = await service.get_article(doc_id)
    article_title = (article or {}).get("title", "") or ""

    extractor = LLMTripletExtractionService()

    q: "queue.Queue[Optional[Dict[str, Any]]]" = queue.Queue()
    result_holder: Dict[str, Any] = {}
    cancel_event = threading.Event()

    def run() -> None:
        try:
            result = extractor.extract(
                doc_id=doc_id,
                text=text,
                article_title=article_title,
                model_id=req.model,
            )
            result_holder["result"] = result
        except Exception as exc:
            logger.exception("LLM extraction failed for %s", doc_id)
            result_holder["error"] = str(exc)
        finally:
            q.put({"type": "done"})

    thread = threading.Thread(target=run, name=f"llm-extract-{doc_id}", daemon=True)
    thread.start()

    async def event_generator():
        try:
            yield _event({"type": "start", "total": 1})
            while True:
                try:
                    evt = q.get_nowait()
                except queue.Empty:
                    await asyncio.sleep(0.2)
                    continue
                if evt["type"] == "done":
                    break
                yield _event(evt)

            if "error" in result_holder:
                yield _event({"type": "error", "message": result_holder["error"]})
                yield "data: [DONE]\n\n"
                return

            result: Dict[str, Any] = result_holder.get("result") or {}
            if result.get("cancelled"):
                yield _event({"type": "cancelled", "message": "Извлечение отменено"})
                yield "data: [DONE]\n\n"
                return
            if not result.get("success"):
                yield _event({"type": "error", "message": result.get("message", "Ошибка извлечения")})
                yield "data: [DONE]\n\n"
                return

            blocks: List[Dict[str, Any]] = result.get("blocks", [])
            if req.save:
                try:
                    saved = await service.save_blocks(doc_id, blocks, user_uid=user["uid"])
                    if not saved.get("success"):
                        logger.warning("save_blocks failed for %s: %s", doc_id, saved.get("message", ""))
                        result["save_error"] = saved.get("message", "Не удалось сохранить блоки")
                except Exception as exc:
                    logger.exception("save_blocks failed for %s", doc_id)
                    result["save_error"] = str(exc)
            yield _event({"type": "result", "data": result})
            yield "data: [DONE]\n\n"
        except GeneratorExit:
            logger.info("Client disconnected during extraction for %s", doc_id)
            cancel_event.set()
            raise

    return StreamingResponse(event_generator(), media_type="text/event-stream")

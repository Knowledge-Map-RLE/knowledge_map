"""
Layer: Interface Adapters — Controller (Web)
Package: web.routers.data_extraction.annotations_ws
Responsibility: WebSocket endpoint для Markdown-аннотаций.
  Одно постоянное соединение на сессию документа заменяет множество HTTP-запросов.
  Протокол: JSON-фреймы, клиент отправляет {action, ...}, сервер отвечает {event, ...}.

Allowed imports: fastapi, application.annotations.*, web.dependencies
Forbidden imports: neomodel (напрямую), infrastructure
"""
import asyncio
import logging
from typing import List, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends

from application.annotations.create_annotation import create_annotation
from application.annotations.get_annotations import get_annotations
from application.annotations.update_annotation import update_annotation
from application.annotations.delete_annotation import delete_annotation
from application.annotations.batch_update_offsets import batch_update_offsets
from web.dependencies import get_annotation_repository, get_document_repository

logger = logging.getLogger(__name__)

router = APIRouter(tags=["annotations-ws"])


# ── Вспомогательная функция сериализации аннотации ──────────────────────────

def _ann_to_dict(ann) -> dict:
    return {
        "uid": ann.uid,
        "text": ann.text,
        "annotation_type": ann.annotation_type,
        "start_offset": ann.start_offset,
        "end_offset": ann.end_offset,
        "color": ann.color,
        "metadata": ann.metadata or {},
        "confidence": ann.confidence,
        "created_date": str(ann.created_date) if ann.created_date else None,
        "source": ann.source,
        "processor_version": ann.processor_version,
    }


# ── Обработчики входящих сообщений ───────────────────────────────────────────

async def _handle_load(
    ws: WebSocket,
    data: dict,
    doc_id: str,
    ann_repo,
    doc_repo,
) -> None:
    """Загружает все аннотации и отправляет чанками по 500 штук."""
    filters = data.get("filters", {})
    types_raw: Optional[str] = filters.get("types")
    source: Optional[str] = filters.get("source") or None

    annotation_types: Optional[List[str]] = (
        [t.strip() for t in types_raw if t.strip()] if isinstance(types_raw, list)
        else [t.strip() for t in types_raw.split(",") if t.strip()] if types_raw
        else None
    )

    anns, total = await asyncio.to_thread(
        get_annotations,
        annotation_repo=ann_repo,
        document_repo=None,
        doc_id=doc_id,
        skip=0,
        limit=None,
        annotation_types=annotation_types,
        source=source,
    )

    if not anns:
        await ws.send_json({"event": "annotations_done", "total": 0})
        return

    chunk_size = 500
    chunks = [anns[i:i + chunk_size] for i in range(0, len(anns), chunk_size)]
    total_chunks = len(chunks)

    for idx, chunk in enumerate(chunks):
        await ws.send_json({
            "event": "annotations_chunk",
            "annotations": [_ann_to_dict(a) for a in chunk],
            "chunk": idx + 1,
            "total_chunks": total_chunks,
        })

    await ws.send_json({"event": "annotations_done", "total": total})


async def _handle_create(
    ws: WebSocket,
    data: dict,
    doc_id: str,
    ann_repo,
    doc_repo,
) -> None:
    request_id = data.get("request_id", "")
    ann = create_annotation(
        annotation_repo=ann_repo,
        document_repo=doc_repo,
        doc_id=doc_id,
        text=data["text"],
        annotation_type=data["annotation_type"],
        start_offset=data["start_offset"],
        end_offset=data["end_offset"],
        color=data.get("color", "#ffeb3b"),
        metadata=data.get("metadata"),
        confidence=data.get("confidence"),
        source="user",
    )
    await ws.send_json({
        "event": "created",
        "request_id": request_id,
        "annotation": _ann_to_dict(ann),
    })


async def _handle_update(
    ws: WebSocket,
    data: dict,
    ann_repo,
) -> None:
    request_id = data.get("request_id", "")
    ann = update_annotation(
        repo=ann_repo,
        annotation_id=data["annotation_id"],
        text=data.get("text"),
        annotation_type=data.get("annotation_type"),
        start_offset=data.get("start_offset"),
        end_offset=data.get("end_offset"),
        color=data.get("color"),
        metadata=data.get("metadata"),
    )
    await ws.send_json({
        "event": "updated",
        "request_id": request_id,
        "annotation": _ann_to_dict(ann),
    })


async def _handle_delete(
    ws: WebSocket,
    data: dict,
    ann_repo,
) -> None:
    request_id = data.get("request_id", "")
    annotation_id = data["annotation_id"]
    delete_annotation(repo=ann_repo, annotation_id=annotation_id)
    await ws.send_json({
        "event": "deleted",
        "request_id": request_id,
        "annotation_id": annotation_id,
    })


async def _handle_batch_update_offsets(
    ws: WebSocket,
    data: dict,
    ann_repo,
) -> None:
    request_id = data.get("request_id", "")
    updates = data.get("updates", [])
    updated_count, errors = batch_update_offsets(repo=ann_repo, updates=updates)
    await ws.send_json({
        "event": "batch_done",
        "request_id": request_id,
        "updated_count": updated_count,
        "errors": errors,
    })


# ── Диспетчер ─────────────────────────────────────────────────────────────────

async def _dispatch(
    ws: WebSocket,
    data: dict,
    doc_id: str,
    ann_repo,
    doc_repo,
) -> None:
    action = data.get("action")
    request_id = data.get("request_id", "")
    try:
        if action == "load":
            await _handle_load(ws, data, doc_id, ann_repo, doc_repo)
        elif action == "create":
            await _handle_create(ws, data, doc_id, ann_repo, doc_repo)
        elif action == "update":
            await _handle_update(ws, data, ann_repo)
        elif action == "delete":
            await _handle_delete(ws, data, ann_repo)
        elif action == "batch_update_offsets":
            await _handle_batch_update_offsets(ws, data, ann_repo)
        else:
            await ws.send_json({
                "event": "error",
                "request_id": request_id,
                "code": 400,
                "detail": f"Unknown action: {action!r}",
            })
    except KeyError as e:
        await ws.send_json({
            "event": "error",
            "request_id": request_id,
            "code": 400,
            "detail": f"Missing field: {e}",
        })
    except Exception as e:
        # Доменные исключения (NotFoundError, DomainValidationError) тоже сюда
        code = getattr(e, "status_code", None)
        if code is None:
            # Определяем код по имени класса
            cls = type(e).__name__
            if "NotFound" in cls:
                code = 404
            elif "Validation" in cls or "Conflict" in cls:
                code = 422
            else:
                code = 500
        logger.exception(f"WS annotation error (action={action}): {e}")
        await ws.send_json({
            "event": "error",
            "request_id": request_id,
            "code": code,
            "detail": str(e),
        })


# ── WebSocket endpoint ────────────────────────────────────────────────────────

@router.websocket("/ws/documents/{doc_id}/annotations")
async def annotations_ws(
    websocket: WebSocket,
    doc_id: str,
    ann_repo=Depends(get_annotation_repository),
    doc_repo=Depends(get_document_repository),
):
    """
    WebSocket-сессия для работы с аннотациями документа.

    Клиент подключается один раз при открытии вкладки Annotator.
    Все операции (load/create/update/delete/batch_update_offsets) идут через это соединение.
    """
    await websocket.accept()
    logger.info(f"WS annotations connected: doc_id={doc_id}")
    
    # Отправляем connected event сразу после подключения
    await websocket.send_json({"event": "connected", "doc_id": doc_id})
    try:
        while True:
            data = await websocket.receive_json()
            await _dispatch(websocket, data, doc_id, ann_repo, doc_repo)
    except WebSocketDisconnect:
        logger.info(f"WS annotations disconnected: doc_id={doc_id}")
    except Exception as e:
        logger.error(f"WS annotations unexpected error: {e}")

"""
Layer: Interface Adapters — Web (Routers)
Package: src.routers.ai_chats
Responsibility: HTTP-контроллеры персистентных AI-чатов (учёт токенов/стоимости).
Все мутации требуют авторизации; ownership проверяется в use cases.

Маршруты:
  GET    /api/ai/chats                — список чатов пользователя
  POST   /api/ai/chats                — создать чат
  GET    /api/ai/chats/{id}/messages  — история сообщений
  POST   /api/ai/chats/{id}/messages  — отправить сообщение (SSE-стрим + usage)
  POST   /api/ai/chats/{id}/messages/estimate — оценка токенов/стоимости
  GET    /api/ai/usage/summary        — агрегат usage за период
"""
import json
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from application.ai_chats.create_chat import create_ai_chat
from application.ai_chats.estimate_message import estimate_message
from application.ai_chats.get_chat import get_ai_chat, get_ai_chat_messages
from application.ai_chats.list_chats import list_ai_chats
from application.ai_chats.send_message import send_ai_message_stream
from application.ai_chats.usage_summary import usage_summary
from domain.exceptions import AuthorizationFailed, NotFoundError
from domain.rules.ai_pricing import calculate_usage_cost
from web.dependencies import (
    get_ai_chat_repository,
    get_ai_gateway,
    get_billing_client,
    get_current_user,
    get_deepseek_tokenizer,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai", tags=["ai_chats"])


class CreateChatRequest(BaseModel):
    title: str = Field(default="", max_length=200)


class EstimateRequest(BaseModel):
    messages: List[dict] = Field(default_factory=list)
    max_output_tokens: Optional[int] = Field(default=None, ge=1, le=1_048_576)


class SendMessageRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=100_000)


@router.get("/chats")
async def list_chats(
    limit: int = 50,
    user: dict = Depends(get_current_user),
    repository=Depends(get_ai_chat_repository),
):
    chats = list_ai_chats(repository=repository, user_uid=user.get("uid", ""), limit=limit)
    return {
        "chats": [
            {
                "id": chat.uid,
                "title": chat.title,
                "model": chat.model,
                "created_at": chat.created_at.isoformat() if chat.created_at else None,
                "updated_at": chat.updated_at.isoformat() if chat.updated_at else None,
            }
            for chat in chats
        ]
    }


@router.post("/chats")
async def create_chat(
    body: CreateChatRequest,
    user: dict = Depends(get_current_user),
    repository=Depends(get_ai_chat_repository),
):
    chat = create_ai_chat(
        repository=repository,
        user_uid=user.get("uid", ""),
        title=body.title,
    )
    return {
        "id": chat.uid,
        "title": chat.title,
        "model": chat.model,
        "created_at": chat.created_at.isoformat() if chat.created_at else None,
    }


@router.get("/chats/{chat_id}/messages")
async def get_messages(
    chat_id: str,
    limit: int = 100,
    user: dict = Depends(get_current_user),
    repository=Depends(get_ai_chat_repository),
):
    try:
        messages = get_ai_chat_messages(
            repository=repository,
            chat_uid=chat_id,
            user_uid=user.get("uid", ""),
            limit=limit,
        )
    except NotFoundError:
        raise HTTPException(status_code=404, detail="chat_not_found")
    except AuthorizationFailed:
        raise HTTPException(status_code=403, detail="forbidden")

    usages = repository.list_usage_for_chat(chat_id, limit=limit)
    usage_by_message = {u.message_uid: u for u in usages}
    # usage привязан к сообщению ассистента; входная часть (input+кэш) проецируется
    # на парное сообщение пользователя, выходная (output+инструменты) — на ассистента.
    return {"messages": [_message_payload(m, usage_by_message, messages) for m in messages]}


def _message_payload(m, usage_by_message: dict, messages) -> dict:
    """Payload сообщения с учётом фактического usage (input-часть на user, output — на assistant)."""
    base = {
        "id": m.uid,
        "role": m.role,
        "content": m.content,
        "created_at": m.created_at.isoformat() if m.created_at else None,
        "tokens": None,
        "cost": None,
        "input_tokens": None,
        "cached_tokens": None,
        "tool_tokens": None,
        "total_tokens": None,
        "cost_breakdown": None,
        "cache_used": False,
    }
    usage = usage_by_message.get(m.uid)
    if m.role == "user":
        # парное сообщение ассистента — следующее в истории
        idx = next((i for i, x in enumerate(messages) if x.uid == m.uid), -1)
        nxt = messages[idx + 1] if idx >= 0 and idx + 1 < len(messages) else None
        if nxt is not None and nxt.role == "assistant":
            usage = usage_by_message.get(nxt.uid)
    if usage is None:
        return base

    if m.role == "user":
        cost = calculate_usage_cost(
            input_tokens=usage.actual_input_tokens,
            cached_input_tokens=usage.actual_cached_tokens,
            output_tokens=0,
            tool_tokens=0,
        )
        base.update(
            {
                "tokens": usage.actual_input_tokens,
                "cost": str(cost.total.normalize()),
                "input_tokens": usage.actual_input_tokens,
                "cached_tokens": usage.actual_cached_tokens,
                "tool_tokens": 0,
                "total_tokens": usage.actual_input_tokens,
                "cost_breakdown": {
                    "input": str(cost.input_cost.normalize()),
                    "cached": str(cost.cached_input_cost.normalize()),
                    "output": "0",
                    "tool": "0",
                },
                "cache_used": bool(usage.actual_cached_tokens),
            }
        )
    else:
        cost = calculate_usage_cost(
            input_tokens=0,
            cached_input_tokens=0,
            output_tokens=usage.actual_output_tokens,
            tool_tokens=usage.actual_tool_tokens,
        )
        base.update(
            {
                "tokens": usage.actual_output_tokens,
                "cost": str(cost.total.normalize()),
                "input_tokens": 0,
                "cached_tokens": 0,
                "tool_tokens": usage.actual_tool_tokens,
                "total_tokens": usage.actual_output_tokens + usage.actual_tool_tokens,
                "cost_breakdown": {
                    "input": "0",
                    "cached": "0",
                    "output": str(cost.output_cost.normalize()),
                    "tool": str(cost.tool_cost.normalize()),
                },
                "cache_used": False,
            }
        )
    return base


@router.post("/chats/{chat_id}/messages/estimate")
async def estimate(
    chat_id: str,
    body: EstimateRequest,
    user: dict = Depends(get_current_user),
    repository=Depends(get_ai_chat_repository),
    tokenizer=Depends(get_deepseek_tokenizer),
):
    try:
        get_ai_chat(repository=repository, chat_uid=chat_id, user_uid=user.get("uid", ""))
    except NotFoundError:
        raise HTTPException(status_code=404, detail="chat_not_found")
    except AuthorizationFailed:
        raise HTTPException(status_code=403, detail="forbidden")
    result = estimate_message(
        tokenizer=tokenizer,
        messages=body.messages,
        max_output_tokens=body.max_output_tokens,
    )
    return result


@router.post("/chats/{chat_id}/messages")
async def send_message(
    chat_id: str,
    body: SendMessageRequest,
    user: dict = Depends(get_current_user),
    repository=Depends(get_ai_chat_repository),
    tokenizer=Depends(get_deepseek_tokenizer),
    gateway=Depends(get_ai_gateway),
    billing=Depends(get_billing_client),
):
    """Отправляет сообщение в AI-чат и стримит ответ (SSE)."""

    async def event_stream():
        async for event in send_ai_message_stream(
            repository=repository,
            tokenizer=tokenizer,
            gateway=gateway,
            billing=billing,
            chat_uid=chat_id,
            user_uid=user.get("uid", ""),
            content=body.content,
        ):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    # Проверка существования/владельца до начала стрима.
    try:
        get_ai_chat(repository=repository, chat_uid=chat_id, user_uid=user.get("uid", ""))
    except NotFoundError:
        raise HTTPException(status_code=404, detail="chat_not_found")
    except AuthorizationFailed:
        raise HTTPException(status_code=403, detail="forbidden")

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/usage/summary")
async def usage_summary_route(
    period: str = "current",
    user: dict = Depends(get_current_user),
    repository=Depends(get_ai_chat_repository),
):
    if period not in ("current", "previous"):
        raise HTTPException(status_code=400, detail="invalid_period")
    return usage_summary(
        repository=repository,
        user_uid=user.get("uid", ""),
        period=period,
    )

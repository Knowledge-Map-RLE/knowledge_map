"""
Layer: Application (Use Cases)
Package: application.ai_chats.send_message
Responsibility: Отправка сообщения в AI-чат со стримингом, учётом токенов,
стоимости и идемпотентным списанием кредитов.

Принадлежит слою Application: оркестрирует репозиторий, шлюз, pricing и
billing-клиент. Не знает о фреймворках. Возвращает async-генератор, который
отдаёт SSE-чанки ответа и по завершении фиксирует фактический usage.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import AsyncIterator, List, Optional

from domain.exceptions import AuthorizationFailed, NotFoundError
from domain.models.ai_chat import AIChat, AIMessage, AIUsage
from domain.rules.ai_pricing import calculate_usage_cost, cost_to_kopecks

logger = logging.getLogger(__name__)


class SendMessageResult:
    """Результат отправки: собраны usage и стоимость."""

    def __init__(self):
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0
        self.cached_tokens = None
        self.tool_tokens = 0
        self.content = ""
        self.provider_request_id = ""
        self.actual_cost = "0"
        self.currency = "RUB"
        self.deducted = False
        self.deduct_error = None


def _check_ownership(repository, chat_uid: str, user_uid: str) -> AIChat:
    chat = repository.get_chat(chat_uid)
    if chat is None:
        raise NotFoundError("AIChat", chat_uid)
    if chat.user_uid != user_uid:
        raise AuthorizationFailed("Чат принадлежит другому пользователю")
    return chat


def _estimate_before_send(tokenizer, messages: List[dict]) -> dict:
    """Оценочная стоимость до отправки (для предварительной проверки кредитов)."""
    try:
        from application.ai_chats.estimate_message import estimate_message

        return estimate_message(tokenizer=tokenizer, messages=messages)
    except Exception as exc:  # pragma: no cover — оценка не критична
        logger.warning("Estimate before send failed: %s", exc)
        return {}


async def send_ai_message_stream(
    *,
    repository,
    tokenizer,
    gateway,
    billing,
    chat_uid: str,
    user_uid: str,
    content: str,
    model: str = "",
) -> AsyncIterator[dict]:
    """Стримит ответ ассистента. Yield-ит dict-события:
    ``{"type": "chunk", "content": ...}`` / ``{"type": "usage", ...}`` /
    ``{"type": "error", ...}`` / ``{"type": "done", ...}``.
    """
    chat = _check_ownership(repository, chat_uid, user_uid)

    history = repository.list_messages(chat_uid, limit=100)
    context: List[dict] = [{"role": m.role, "content": m.content} for m in history]
    if content:
        context.append({"role": "user", "content": content})

    # Сохраняем сообщение пользователя.
    user_order = len(history) + 1
    user_msg = AIMessage(
        uid=str(uuid.uuid4()),
        chat_uid=chat_uid,
        role="user",
        content=content,
        order=user_order,
        created_at=datetime.utcnow(),
    )
    repository.add_message(user_msg)

    # Оценка до отправки (только для предупреждения, не финансовый источник).
    estimated = _estimate_before_send(tokenizer, context)

    result = SendMessageResult()
    if estimated:
        result.prompt_tokens = estimated.get("estimated_input_tokens", 0)
        result.completion_tokens = estimated.get("estimated_output_tokens", 0)

    try:
        async for chunk_data in gateway.stream_chat_completions(
            messages=context,
            model=model or chat.model,
        ):
            if chunk_data == "[DONE]":
                break
            try:
                payload = json.loads(chunk_data)
            except json.JSONDecodeError:
                continue
            usage = payload.get("usage") or {}
            if usage:
                result.prompt_tokens = int(usage.get("prompt_tokens") or 0)
                result.completion_tokens = int(usage.get("completion_tokens") or 0)
                result.total_tokens = int(usage.get("total_tokens") or 0)
                cached = (
                    usage.get("prompt_cache_hit_tokens")
                    or usage.get("cached_tokens")
                    or (usage.get("prompt_tokens_details") or {}).get("cached_tokens")
                )
                result.cached_tokens = int(cached) if cached else None
                tool = usage.get("tool_tokens") or 0
                result.tool_tokens = int(tool)
            delta = (
                (payload.get("choices") or [{}])[0].get("delta") or {}
            ).get("content")
            if delta:
                result.content += delta
                yield {"type": "chunk", "content": delta}
            provider_id = payload.get("id")
            if provider_id:
                result.provider_request_id = str(provider_id)
    except Exception as exc:  # pragma: no cover
        logger.exception("AI gateway streaming failed")
        yield {"type": "error", "message": str(exc)}
        return

    # Расчёт фактической стоимости.
    if result.total_tokens or result.completion_tokens:
        cost = calculate_usage_cost(
            input_tokens=result.prompt_tokens,
            cached_input_tokens=result.cached_tokens or 0,
            output_tokens=result.completion_tokens,
            tool_tokens=result.tool_tokens,
        )
        result.actual_cost = str(cost.total)

    assistant_order = user_order + 1
    assistant_msg = AIMessage(
        uid=str(uuid.uuid4()),
        chat_uid=chat_uid,
        role="assistant",
        content=result.content,
        order=assistant_order,
        created_at=datetime.utcnow(),
    )
    repository.add_message(assistant_msg)
    repository.touch_chat(chat_uid)

    # Учёт фактического usage.
    usage_record = AIUsage(
        uid=str(uuid.uuid4()),
        message_uid=assistant_msg.uid,
        chat_uid=chat_uid,
        user_uid=user_uid,
        model=model or chat.model,
        provider_request_id=result.provider_request_id or str(uuid.uuid4()),
        estimated_input_tokens=result.prompt_tokens,
        estimated_output_tokens=result.completion_tokens,
        estimated_cached_tokens=None,
        estimated_cost=estimated.get("estimated_cost", "0"),
        actual_input_tokens=result.prompt_tokens,
        actual_cached_tokens=result.cached_tokens or 0,
        actual_output_tokens=result.completion_tokens,
        actual_tool_tokens=result.tool_tokens,
        actual_cost=result.actual_cost,
        currency=result.currency,
    )
    repository.save_usage(usage_record)

    # Идемпотентное списание через billing.
    amount_kopecks = cost_to_kopecks(_decimal(result.actual_cost)) if result.actual_cost != "0" else 0
    if amount_kopecks > 0:
        try:
            deduct = billing.deduct_credits(
                user_id=user_uid,
                amount=amount_kopecks,
                reference_id=usage_record.provider_request_id,
                description=f"AI usage chat={chat_uid}",
            )
            result.deducted = bool(deduct.get("ok"))
            if not result.deducted:
                result.deduct_error = deduct.get("error")
        except Exception as exc:
            result.deducted = False
            result.deduct_error = str(exc)

    yield {
        "type": "usage",
        "message_uid": assistant_msg.uid,
        "prompt_tokens": result.prompt_tokens,
        "cached_tokens": result.cached_tokens or 0,
        "completion_tokens": result.completion_tokens,
        "tool_tokens": result.tool_tokens,
        "total_tokens": result.total_tokens,
        "cost": result.actual_cost,
        "cost_breakdown": _cost_breakdown(
            input_tokens=result.prompt_tokens,
            cached_input_tokens=result.cached_tokens or 0,
            output_tokens=result.completion_tokens,
            tool_tokens=result.tool_tokens,
        ),
        "currency": result.currency,
        "deducted": result.deducted,
        "deduct_error": result.deduct_error,
    }
    yield {"type": "done"}


def _cost_breakdown(
    *,
    input_tokens: int,
    cached_input_tokens: int,
    output_tokens: int,
    tool_tokens: int,
) -> dict:
    """Разбивка стоимости по компонентам (вход/кэш/выход/инструменты)."""
    cost = calculate_usage_cost(
        input_tokens=input_tokens,
        cached_input_tokens=cached_input_tokens,
        output_tokens=output_tokens,
        tool_tokens=tool_tokens,
    )
    return {
        "input": str(cost.input_cost.normalize()),
        "cached": str(cost.cached_input_cost.normalize()),
        "output": str(cost.output_cost.normalize()),
        "tool": str(cost.tool_cost.normalize()),
    }


def _decimal(value: str):
    from decimal import Decimal

    try:
        return Decimal(value)
    except Exception:
        return Decimal("0")

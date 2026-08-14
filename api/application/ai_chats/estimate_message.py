"""
Layer: Application (Use Cases)
Package: application.ai_chats.estimate_message
Responsibility: Оценка токенов и стоимости сообщения до отправки.

Принадлежит слою Application: оркестрирует токенизатор и pricing, не знает
о фреймворках. Оценка НЕ является финансовым источником — фактический usage
приходит от провайдера после ответа.
"""
from __future__ import annotations

from typing import List, Optional

from domain.rules.ai_pricing import estimate_usage_cost


def estimate_message(
    *,
    tokenizer,
    messages: List[dict],
    max_output_tokens: Optional[int] = None,
) -> dict:
    estimated = tokenizer.estimate_messages_usage(messages, max_output_tokens=max_output_tokens)
    cost = estimate_usage_cost(
        estimated_input_tokens=estimated["estimated_input_tokens"],
        estimated_output_tokens=estimated["estimated_output_tokens"],
        cached_input_tokens=None,
    )
    return {
        "estimated_input_tokens": estimated["estimated_input_tokens"],
        "estimated_output_tokens": estimated["estimated_output_tokens"],
        "estimated_cached_tokens": None,
        "estimated_cost": str(cost.total),
        "estimated_max_cost": str(cost.total),
        "cost_breakdown": {
            "input": str(cost.input_cost.normalize()),
            "cached": str(cost.cached_input_cost.normalize()),
            "output": str(cost.output_cost.normalize()),
            "tool": str(cost.tool_cost.normalize()),
        },
        "currency": "RUB",
        "is_estimate": True,
    }

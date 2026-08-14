"""
Layer: Application (Use Cases)
Package: application.ai_chats.usage_summary
Responsibility: Агрегация AI-usage пользователя за период.

Принадлежит слою Application: оркестрирует репозиторий и Decimal-арифметику.
Возвращает суммы токенов и стоимости за период, без финансовых float.
"""
from __future__ import annotations

import calendar
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional

from domain.models.ai_chat import AIUsage


def _month_start_timestamp(offset_months: int) -> float:
    """Начало месяца (UTC) как unix-время.

    neomodel DateTimeProperty в этом проекте сохраняется как unix timestamp,
    поэтому период для фильтрации тоже выражается в unix-времени.
    """
    now = datetime.now(timezone.utc)
    year, month = now.year, now.month
    for _ in range(offset_months):
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    first_utc = calendar.timegm((year, month, 1, 0, 0, 0))
    return float(first_utc)


def _period_start(period: str) -> Optional[float]:
    if period == "current":
        return _month_start_timestamp(0)
    if period == "previous":
        return _month_start_timestamp(1)
    return None


def usage_summary(
    *,
    repository,
    user_uid: str,
    period: str = "current",
    limit: int = 100,
) -> dict:
    since = _period_start(period)
    usages: List[AIUsage] = repository.list_usage_for_user(
        user_uid, since=since, limit=limit
    )

    input_tokens = 0
    cached_tokens = 0
    output_tokens = 0
    tool_tokens = 0
    total_cost = Decimal("0")
    request_count = 0

    for usage in usages:
        input_tokens += usage.actual_input_tokens
        cached_tokens += usage.actual_cached_tokens
        output_tokens += usage.actual_output_tokens
        tool_tokens += usage.actual_tool_tokens
        try:
            total_cost += Decimal(usage.actual_cost)
        except Exception:
            pass
        request_count += 1

    return {
        "period": period,
        "input_tokens": input_tokens,
        "cached_tokens": cached_tokens,
        "output_tokens": output_tokens,
        "tool_tokens": tool_tokens,
        "total_tokens": input_tokens + cached_tokens + output_tokens + tool_tokens,
        "cost": str(total_cost.normalize()),
        "currency": "RUB",
        "request_count": request_count,
    }

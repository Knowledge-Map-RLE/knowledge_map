"""
Layer: Domain
Package: domain.rules.subscription_rules
Responsibility: Правила подписки: период, активность, доступ к тарифам.
"""
from datetime import datetime, timedelta
from typing import Optional

from ..models.plan import Plan
from ..models.subscription import Subscription, SubscriptionStatus

FREE_PLAN_CODE = "FREE"


def add_one_month(dt: datetime) -> datetime:
    """Добавляет один календарный месяц (с удержанием дня месяца)."""
    if dt.month == 12:
        year, month = dt.year + 1, 1
    else:
        year, month = dt.year, dt.month + 1
    day = min(dt.day, _days_in_month(year, month))
    return datetime(year, month, day, dt.hour, dt.minute, dt.second, dt.microsecond)


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        return 31
    return (datetime(year, month + 1, 1) - timedelta(days=1)).day


def compute_period(plan: Plan, from_when: Optional[datetime] = None) -> tuple[datetime, datetime]:
    """Период действия тарифа: [start, end). Если план бесплатный — период не создаётся."""
    if plan.period != "month":
        raise ValueError(f"Unsupported plan period: {plan.period!r}")
    start = from_when or datetime.utcnow()
    return start, add_one_month(start)


def is_active(subscription: Subscription, now: datetime) -> bool:
    if subscription.status != SubscriptionStatus.ACTIVE:
        return False
    return now < subscription.current_period_end


def effective_plan_code(subscription: Optional[Subscription], now: datetime) -> str:
    """Текущий эффективный тариф пользователя. Без активной подписки — FREE."""
    if subscription is None:
        return FREE_PLAN_CODE
    if not is_active(subscription, now):
        return FREE_PLAN_CODE
    return subscription.plan_code


def can_use(subscription: Optional[Subscription], required_plan: str, now: datetime) -> bool:
    """Проверка доступа к функции тарифа. Max включает Pro."""
    if required_plan == FREE_PLAN_CODE:
        return True
    current = effective_plan_code(subscription, now)
    if current == required_plan:
        return True
    if required_plan == "PRO" and current == "MAX":
        return True
    return False


def period_extended(old_end: Optional[datetime], new_end: datetime) -> bool:
    """Расширился ли период подписки (защита от повторного начисления кредитов)."""
    if old_end is None:
        return True
    return new_end > old_end

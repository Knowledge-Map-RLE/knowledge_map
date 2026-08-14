"""Тесты правил подписки: период, активность, доступ к тарифам."""
from datetime import datetime

import pytest

from domain.models import Plan, Subscription
from domain.models.subscription import SubscriptionStatus
from domain.rules.subscription_rules import (
    add_one_month,
    can_use,
    compute_period,
    effective_plan_code,
    is_active,
)

PRO_PLAN = Plan(code="PRO", name="Pro", price_kopecks=150000, credit_limit=10000)


def _dt(year, month, day):
    return datetime(year, month, day, 12, 0, 0)


@pytest.mark.parametrize(
    "dt,expected",
    [
        (_dt(2026, 1, 15), _dt(2026, 2, 15)),
        (_dt(2026, 12, 15), _dt(2027, 1, 15)),
        (_dt(2026, 1, 31), _dt(2026, 2, 28)),
        (_dt(2028, 1, 31), _dt(2028, 2, 29)),
        (_dt(2026, 8, 31), _dt(2026, 9, 30)),
    ],
)
def test_add_one_month(dt, expected):
    assert add_one_month(dt) == expected


def test_compute_period():
    start = _dt(2026, 1, 15)
    period_start, period_end = compute_period(PRO_PLAN, from_when=start)
    assert period_start == start
    assert period_end == _dt(2026, 2, 15)


def test_compute_period_rejects_unknown_period():
    plan = Plan(code="X", name="X", price_kopecks=0, period="year")
    with pytest.raises(ValueError):
        compute_period(plan, from_when=_dt(2026, 1, 1))


def _active_sub(end: datetime) -> Subscription:
    return Subscription(
        uid="sub-1",
        user_id="user-1",
        plan_code="PRO",
        status=SubscriptionStatus.ACTIVE,
        current_period_start=_dt(2026, 1, 1),
        current_period_end=end,
    )


def test_is_active_true():
    sub = _active_sub(_dt(2026, 2, 1))
    assert is_active(sub, _dt(2026, 1, 15)) is True


def test_is_active_false_after_end():
    sub = _active_sub(_dt(2026, 1, 10))
    assert is_active(sub, _dt(2026, 1, 15)) is False


def test_is_active_false_cancelled():
    sub = _active_sub(_dt(2026, 2, 1))
    sub.status = SubscriptionStatus.CANCELLED
    assert is_active(sub, _dt(2026, 1, 15)) is False


def test_effective_plan_code_free_without_subscription():
    assert effective_plan_code(None, _dt(2026, 1, 15)) == "FREE"


def test_effective_plan_code_active():
    assert effective_plan_code(_active_sub(_dt(2026, 2, 1)), _dt(2026, 1, 15)) == "PRO"


def test_effective_plan_code_falls_back_to_free_when_expired():
    assert effective_plan_code(_active_sub(_dt(2026, 1, 10)), _dt(2026, 1, 15)) == "FREE"


@pytest.mark.parametrize(
    "sub,required,expected",
    [
        (None, "FREE", True),
        (None, "PRO", False),
        (_active_sub(_dt(2026, 2, 1)), "PRO", True),
        (_active_sub(_dt(2026, 2, 1)), "MAX", False),
        (_active_sub(_dt(2026, 1, 10)), "PRO", False),
    ],
)
def test_can_use(sub, required, expected):
    assert can_use(sub, required, _dt(2026, 1, 15)) is expected


def test_can_use_max_includes_pro():
    sub = Subscription(
        uid="sub-max",
        user_id="user-1",
        plan_code="MAX",
        status=SubscriptionStatus.ACTIVE,
        current_period_start=_dt(2026, 1, 1),
        current_period_end=_dt(2026, 2, 1),
    )
    assert can_use(sub, "PRO", _dt(2026, 1, 15)) is True

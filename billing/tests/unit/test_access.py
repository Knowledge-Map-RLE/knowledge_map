"""Тесты проверки доступа (CheckAccess) и состояния подписки (GetSubscription)."""
from datetime import datetime

from application.access.check_access import CheckAccess
from application.subscriptions.get_subscription import GetSubscription
from domain.models import Subscription
from domain.models.subscription import SubscriptionStatus


def _make_sub(plan_code="PRO", end_year=2026, end_month=2):
    return Subscription(
        uid=f"sub-{plan_code}",
        user_id="user-1",
        plan_code=plan_code,
        status=SubscriptionStatus.ACTIVE,
        current_period_start=None,
        current_period_end=datetime(end_year, end_month, 1, 12, 0, 0),
    )


def test_access_free_allowed(repos, now):
    access = CheckAccess(subscription_repository=repos["subscriptions"])
    decision = access.execute(user_id="user-1", required_plan="FREE", now=now)
    assert decision.allowed is True
    assert decision.plan_code == "FREE"


def test_access_pro_denied_for_free(repos, now):
    access = CheckAccess(subscription_repository=repos["subscriptions"])
    decision = access.execute(user_id="user-1", required_plan="PRO", now=now)
    assert decision.allowed is False
    assert decision.reason == "PLAN_REQUIRED:PRO"


def test_access_pro_allowed_with_subscription(repos, now):
    repos["subscriptions"].save(_make_sub("PRO"))
    access = CheckAccess(subscription_repository=repos["subscriptions"])
    decision = access.execute(user_id="user-1", required_plan="PRO", now=now)
    assert decision.allowed is True
    assert decision.plan_code == "PRO"


def test_access_max_allows_pro(repos, now):
    repos["subscriptions"].save(_make_sub("MAX"))
    access = CheckAccess(subscription_repository=repos["subscriptions"])
    assert access.execute(user_id="user-1", required_plan="PRO", now=now).allowed is True
    assert access.execute(user_id="user-1", required_plan="MAX", now=now).allowed is True


def test_access_expired_subscription_is_free(repos, now):
    repos["subscriptions"].save(_make_sub("PRO", end_year=2025))
    access = CheckAccess(subscription_repository=repos["subscriptions"])
    decision = access.execute(user_id="user-1", required_plan="PRO", now=now)
    assert decision.allowed is False
    assert decision.plan_code == "FREE"


def test_subscription_state_free_user(repos, now):
    get_sub = GetSubscription(
        subscription_repository=repos["subscriptions"],
        credit_repository=repos["credits"],
        plan_repository=repos["plans"],
    )
    state = get_sub.execute(user_id="user-1", now=now)
    assert state.active is False
    assert state.plan_code == "FREE"
    assert state.credits_limit == 100


def test_subscription_state_pro_user(repos, now):
    repos["subscriptions"].save(_make_sub("PRO"))
    repos["credits"].get_or_create_account("user-1").balance = 5000
    get_sub = GetSubscription(
        subscription_repository=repos["subscriptions"],
        credit_repository=repos["credits"],
        plan_repository=repos["plans"],
    )
    state = get_sub.execute(user_id="user-1", now=now)
    assert state.active is True
    assert state.plan_code == "PRO"
    assert state.credits_balance == 5000
    assert state.credits_limit == 10000

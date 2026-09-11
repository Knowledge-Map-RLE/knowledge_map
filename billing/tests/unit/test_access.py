"""Тесты проверки доступа (CheckAccess) и состояния подписки (GetSubscription)."""
from datetime import datetime

from application.access.check_access import CheckAccess
from application.subscriptions.get_subscription import GetSubscription
from domain.models import Subscription
from domain.models.subscription import SubscriptionStatus


def _make_sub(plan_code="TOKENS_50M", end_year=2099, end_month=12):
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


def test_access_paid_denied_for_free(repos, now):
    access = CheckAccess(subscription_repository=repos["subscriptions"])
    decision = access.execute(user_id="user-1", required_plan="TOKENS_50M", now=now)
    assert decision.allowed is False
    assert decision.reason == "PLAN_REQUIRED:TOKENS_50M"


def test_access_paid_allowed_with_subscription(repos, now):
    repos["subscriptions"].save(_make_sub("TOKENS_50M"))
    access = CheckAccess(subscription_repository=repos["subscriptions"])
    decision = access.execute(user_id="user-1", required_plan="TOKENS_50M", now=now)
    assert decision.allowed is True
    assert decision.plan_code == "TOKENS_50M"


def test_access_expired_subscription_is_free(repos, now):
    repos["subscriptions"].save(_make_sub("TOKENS_50M", end_year=2025))
    access = CheckAccess(subscription_repository=repos["subscriptions"])
    decision = access.execute(user_id="user-1", required_plan="TOKENS_50M", now=now)
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
    assert state.token_balance == 0


def test_subscription_state_paid_user(repos, now):
    repos["subscriptions"].save(_make_sub("TOKENS_50M"))
    repos["credits"].get_or_create_account("user-1").balance = 30_000_000
    get_sub = GetSubscription(
        subscription_repository=repos["subscriptions"],
        credit_repository=repos["credits"],
        plan_repository=repos["plans"],
    )
    state = get_sub.execute(user_id="user-1", now=now)
    assert state.active is True
    assert state.plan_code == "TOKENS_50M"
    assert state.token_balance == 30_000_000

"""Тесты активации/продления подписки (ActivateSubscription)."""
import pytest

from application.subscriptions.activate_subscription import ActivateSubscription
from domain.exceptions import PlanNotFoundError
from domain.models import Subscription
from domain.models.subscription import SubscriptionStatus


@pytest.fixture
def activator(repos):
    return ActivateSubscription(
        subscription_repository=repos["subscriptions"],
        plan_repository=repos["plans"],
        credit_repository=repos["credits"],
    )


def test_activate_new_subscription(activator, repos, now):
    result = activator.execute(
        user_id="user-1", plan_code="PRO", payment_uid="pay-1", now=now
    )

    assert result.credits_granted == 10000
    sub = repos["subscriptions"].get_active_by_user("user-1")
    assert sub is not None
    assert sub.plan_code == "PRO"
    assert sub.status == SubscriptionStatus.ACTIVE
    assert sub.current_period_end > now
    assert repos["credits"].get_balance("user-1") == 10000


def test_activate_free_plan_grants_credits(activator, repos, now):
    result = activator.execute(
        user_id="user-1", plan_code="FREE", payment_uid=None, now=now
    )

    assert result.credits_granted == 100
    assert repos["credits"].get_balance("user-1") == 100


def test_unknown_plan_raises(activator, repos, now):
    with pytest.raises(PlanNotFoundError):
        activator.execute(user_id="user-1", plan_code="NOPE", payment_uid="pay-1", now=now)


def test_extension_stacks_period(activator, repos, now):
    activator.execute(user_id="user-1", plan_code="PRO", payment_uid="pay-1", now=now)
    sub_before = repos["subscriptions"].get_active_by_user("user-1")

    activator.execute(user_id="user-1", plan_code="PRO", payment_uid="pay-2", now=now)
    sub_after = repos["subscriptions"].get_active_by_user("user-1")

    assert sub_after.current_period_end > sub_before.current_period_end
    assert repos["credits"].get_balance("user-1") == 20000


def test_activation_keeps_existing_when_cancelled(activator, repos, now):
    activator.execute(user_id="user-1", plan_code="PRO", payment_uid="pay-1", now=now)
    sub = repos["subscriptions"].get_active_by_user("user-1")
    sub.cancel_at_period_end = True
    repos["subscriptions"].save(sub)

    activator.execute(user_id="user-1", plan_code="PRO", payment_uid="pay-2", now=now)
    sub = repos["subscriptions"].get_active_by_user("user-1")
    assert sub.cancel_at_period_end is False

"""
Layer: Application
Package: application.subscriptions.get_subscription
Responsibility: Получение текущего состояния подписки пользователя.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from application.ports.repositories import (
    CreditRepositoryProtocol,
    PlanRepositoryProtocol,
    SubscriptionRepositoryProtocol,
)
from domain.models import Subscription
from domain.rules.subscription_rules import effective_plan_code


@dataclass(frozen=True)
class SubscriptionState:
    active: bool
    plan_code: str
    status: Optional[str]
    current_period_start: Optional[str]
    current_period_end: Optional[str]
    cancel_at_period_end: bool
    token_balance: int


class GetSubscription:
    def __init__(
        self,
        subscription_repository: SubscriptionRepositoryProtocol,
        credit_repository: CreditRepositoryProtocol,
        plan_repository: PlanRepositoryProtocol,
    ):
        self._subscription_repository = subscription_repository
        self._credit_repository = credit_repository
        self._plan_repository = plan_repository

    def execute(self, *, user_id: str, now: datetime) -> SubscriptionState:
        subscription = self._subscription_repository.get_active_by_user(user_id)
        plan_code = effective_plan_code(subscription, now)
        token_balance = self._credit_repository.get_balance(user_id)
        return SubscriptionState(
            active=plan_code != "FREE",
            plan_code=plan_code,
            status=subscription.status if subscription else None,
            current_period_start=_iso(subscription.current_period_start) if subscription else None,
            current_period_end=_iso(subscription.current_period_end) if subscription else None,
            cancel_at_period_end=bool(subscription and subscription.cancel_at_period_end),
            token_balance=token_balance,
        )


def _iso(dt) -> str:
    return dt.isoformat() if dt else None

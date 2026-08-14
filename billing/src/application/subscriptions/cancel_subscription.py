"""
Layer: Application
Package: application.subscriptions.cancel_subscription
Responsibility: Отмена подписки с конца оплаченного периода.
"""
from datetime import datetime

from application.ports.repositories import SubscriptionRepositoryProtocol
from domain.exceptions import SubscriptionNotFoundError


class CancelSubscription:
    def __init__(self, subscription_repository: SubscriptionRepositoryProtocol):
        self._subscription_repository = subscription_repository

    def execute(self, *, user_id: str, now: datetime) -> None:
        subscription = self._subscription_repository.get_active_by_user(user_id)
        if subscription is None:
            raise SubscriptionNotFoundError("No active subscription")
        subscription.cancel_at_period_end = True
        self._subscription_repository.save(subscription)

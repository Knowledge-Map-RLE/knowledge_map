"""
Layer: Application
Package: application.subscriptions.activate_subscription
Responsibility: Активация/продление подписки и начисление месячных кредитов.
"""
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from application.ports.repositories import (
    CreditRepositoryProtocol,
    PlanRepositoryProtocol,
    SubscriptionRepositoryProtocol,
)
from domain.exceptions import PlanNotFoundError
from domain.models import CreditTransaction, Subscription
from domain.models.credit import CreditTransactionType
from domain.models.subscription import SubscriptionStatus
from domain.rules.subscription_rules import add_one_month


@dataclass(frozen=True)
class SubscriptionActivation:
    subscription: Subscription
    credits_granted: int


class ActivateSubscription:
    def __init__(
        self,
        subscription_repository: SubscriptionRepositoryProtocol,
        plan_repository: PlanRepositoryProtocol,
        credit_repository: CreditRepositoryProtocol,
    ):
        self._subscription_repository = subscription_repository
        self._plan_repository = plan_repository
        self._credit_repository = credit_repository

    def execute(
        self,
        *,
        user_id: str,
        plan_code: str,
        payment_uid: str,
        now: datetime,
    ) -> SubscriptionActivation:
        plan = self._plan_repository.get_by_code(plan_code)
        if plan is None:
            raise PlanNotFoundError(f"Plan {plan_code!r} not found")

        subscription = self._subscription_repository.get_active_by_user(user_id)

        if subscription is None:
            period_start = now
            period_end = add_one_month(now)
            subscription = Subscription(
                uid=str(uuid.uuid4()),
                user_id=user_id,
                plan_code=plan.code,
                status=SubscriptionStatus.ACTIVE,
                started_at=now,
                current_period_start=period_start,
                current_period_end=period_end,
                cancel_at_period_end=False,
            )
        else:
            old_end = subscription.current_period_end
            period_start = max(now, old_end)
            period_end = add_one_month(period_start)
            subscription.plan_code = plan.code
            subscription.status = SubscriptionStatus.ACTIVE
            subscription.current_period_start = period_start
            subscription.current_period_end = period_end
            subscription.cancel_at_period_end = False

        self._subscription_repository.save(subscription)

        credits_granted = plan.credit_limit
        if credits_granted > 0:
            account = self._credit_repository.get_or_create_account(user_id)
            self._credit_repository.apply_transaction(
                CreditTransaction(
                    uid=str(uuid.uuid4()),
                    account_uid=account.uid,
                    user_id=user_id,
                    amount=credits_granted,
                    type=CreditTransactionType.SUBSCRIPTION_GRANT,
                    reference_id=payment_uid,
                    description=f"Тариф {plan.code}: {credits_granted} кредитов за месяц",
                )
            )

        return SubscriptionActivation(
            subscription=subscription,
            credits_granted=credits_granted,
        )

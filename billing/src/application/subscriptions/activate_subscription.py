"""
Layer: Application
Package: application.subscriptions.activate_subscription
Responsibility: Активация подписки и начисление токенов.

При покупке пакета токенов:
  - Создаётся/продлевается подписка (бессрочный период для токенов).
  - Токены начисляются на баланс пользователя.
  - Пользователь может покупать несколько пакетов — токены суммируются.
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
from domain.rules.subscription_rules import compute_period


@dataclass(frozen=True)
class SubscriptionActivation:
    subscription: Subscription
    tokens_granted: int


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
            period_start, period_end = compute_period(plan, from_when=now)
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
            _, new_end = compute_period(plan, from_when=now)
            subscription.plan_code = plan.code
            subscription.status = SubscriptionStatus.ACTIVE
            subscription.current_period_end = new_end
            subscription.cancel_at_period_end = False

        self._subscription_repository.save(subscription)

        tokens_granted = plan.tokens_granted
        if tokens_granted > 0:
            account = self._credit_repository.get_or_create_account(user_id)
            self._credit_repository.apply_transaction(
                CreditTransaction(
                    uid=str(uuid.uuid4()),
                    account_uid=account.uid,
                    user_id=user_id,
                    amount=tokens_granted,
                    type=CreditTransactionType.SUBSCRIPTION_GRANT,
                    reference_id=payment_uid,
                    description=f"Пакет {plan.code}: +{tokens_granted:,} токенов",
                )
            )

        return SubscriptionActivation(
            subscription=subscription,
            tokens_granted=tokens_granted,
        )

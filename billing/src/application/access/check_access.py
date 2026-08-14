"""
Layer: Application
Package: application.access.check_access
Responsibility: Проверка доступа пользователя к функциям тарифа.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from application.ports.repositories import SubscriptionRepositoryProtocol
from domain.rules.subscription_rules import can_use, effective_plan_code


@dataclass(frozen=True)
class AccessDecision:
    allowed: bool
    plan_code: str
    required_plan: str
    reason: Optional[str] = None


class CheckAccess:
    def __init__(self, subscription_repository: SubscriptionRepositoryProtocol):
        self._subscription_repository = subscription_repository

    def execute(self, *, user_id: str, required_plan: str, now: datetime) -> AccessDecision:
        subscription = self._subscription_repository.get_active_by_user(user_id)
        plan_code = effective_plan_code(subscription, now)
        allowed = can_use(subscription, required_plan, now)
        return AccessDecision(
            allowed=allowed,
            plan_code=plan_code,
            required_plan=required_plan,
            reason=None if allowed else f"PLAN_REQUIRED:{required_plan}",
        )

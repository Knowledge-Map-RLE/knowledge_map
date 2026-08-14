"""
Layer: Interface Adapters
Package: adapters.repositories.subscription_repository
Responsibility: Репозиторий подписок (Subscription) на neomodel.
"""
from typing import List, Optional

from domain.models import Subscription
from domain.models.subscription import SubscriptionStatus
from infrastructure.neo4j_models import SubscriptionNode


class SubscriptionRepository:
    def get_active_by_user(self, user_id: str) -> Optional[Subscription]:
        nodes = list(
            SubscriptionNode.nodes.filter(
                user_id=user_id, status=SubscriptionStatus.ACTIVE
            ).order_by("-current_period_end")
        )
        return self._to_domain(nodes[0]) if nodes else None

    def get_by_uid(self, uid: str) -> Optional[Subscription]:
        node = SubscriptionNode.nodes.get_or_none(uid=uid)
        return self._to_domain(node) if node else None

    def list_by_user(self, user_id: str) -> List[Subscription]:
        nodes = SubscriptionNode.nodes.filter(user_id=user_id).order_by("-current_period_end")
        return [self._to_domain(node) for node in nodes]

    def save(self, subscription: Subscription) -> Subscription:
        node = SubscriptionNode.nodes.get_or_none(uid=subscription.uid)
        if node is None:
            node = SubscriptionNode(uid=subscription.uid)
        node.user_id = subscription.user_id
        node.plan_code = subscription.plan_code
        node.status = subscription.status
        node.started_at = subscription.started_at
        node.current_period_start = subscription.current_period_start
        node.current_period_end = subscription.current_period_end
        node.cancel_at_period_end = subscription.cancel_at_period_end
        node.created_at = subscription.created_at
        node.save()
        return self._to_domain(node)

    @staticmethod
    def _to_domain(node: SubscriptionNode) -> Subscription:
        return Subscription(
            uid=node.uid,
            user_id=node.user_id,
            plan_code=node.plan_code,
            status=node.status,
            started_at=node.started_at,
            current_period_start=node.current_period_start,
            current_period_end=node.current_period_end,
            cancel_at_period_end=node.cancel_at_period_end,
            created_at=node.created_at,
        )

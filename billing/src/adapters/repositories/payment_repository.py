"""
Layer: Interface Adapters
Package: adapters.repositories.payment_repository
Responsibility: Репозиторий платежей (Payment) на neomodel.
"""
from datetime import datetime
from typing import List, Optional

from domain.models import Payment
from domain.models.payment import PaymentStatus
from infrastructure.neo4j_models import PaymentNode


class PaymentRepository:
    def create(self, payment: Payment) -> Payment:
        node = PaymentNode(
            uid=payment.uid,
            user_id=payment.user_id,
            subscription_uid=payment.subscription_uid,
            provider=payment.provider,
            provider_payment_id=payment.provider_payment_id,
            amount_kopecks=payment.amount_kopecks,
            currency=payment.currency,
            status=payment.status,
            confirmation_url=payment.confirmation_url,
            description=payment.description,
            metadata=payment.metadata,
            created_at=payment.created_at,
            updated_at=payment.updated_at,
        )
        node.save()
        return self._to_domain(node)

    def save(self, payment: Payment) -> Payment:
        node = PaymentNode.nodes.get(uid=payment.uid)
        node.user_id = payment.user_id
        node.subscription_uid = payment.subscription_uid
        node.provider = payment.provider
        node.provider_payment_id = payment.provider_payment_id
        node.amount_kopecks = payment.amount_kopecks
        node.currency = payment.currency
        node.status = payment.status
        node.confirmation_url = payment.confirmation_url
        node.description = payment.description
        node.metadata = payment.metadata
        node.updated_at = payment.updated_at
        node.save()
        return self._to_domain(node)

    def get_by_uid(self, uid: str) -> Optional[Payment]:
        node = PaymentNode.nodes.get_or_none(uid=uid)
        return self._to_domain(node) if node else None

    def get_by_provider_id(self, provider_payment_id: str) -> Optional[Payment]:
        nodes = list(
            PaymentNode.nodes.filter(provider_payment_id=provider_payment_id)
        )
        return self._to_domain(nodes[0]) if nodes else None

    def list_by_user(self, user_id: str, limit: int = 50) -> List[Payment]:
        nodes = PaymentNode.nodes.filter(user_id=user_id).order_by("-created_at")[:limit]
        return [self._to_domain(node) for node in nodes]

    def list_pending_since(self, since: datetime) -> List[Payment]:
        nodes = (
            PaymentNode.nodes.filter(
                status__in=[PaymentStatus.CREATED, PaymentStatus.PENDING],
                created_at__lt=since,
            )
            .order_by("created_at")
        )
        return [self._to_domain(node) for node in nodes]

    @staticmethod
    def _to_domain(node: PaymentNode) -> Payment:
        return Payment(
            uid=node.uid,
            user_id=node.user_id,
            subscription_uid=node.subscription_uid,
            provider=node.provider,
            provider_payment_id=node.provider_payment_id,
            amount_kopecks=node.amount_kopecks,
            currency=node.currency,
            status=node.status,
            confirmation_url=node.confirmation_url,
            description=node.description,
            metadata=node.metadata,
            created_at=node.created_at,
            updated_at=node.updated_at,
        )

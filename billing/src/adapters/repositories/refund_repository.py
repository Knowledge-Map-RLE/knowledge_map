"""
Layer: Interface Adapters
Package: adapters.repositories.refund_repository
Responsibility: Репозиторий возвратов (Refund) на neomodel.
"""
from typing import List, Optional

from domain.models import Refund
from infrastructure.neo4j_models import RefundNode


class RefundRepository:
    def create(self, refund: Refund) -> Refund:
        node = RefundNode(
            uid=refund.uid,
            payment_uid=refund.payment_uid,
            provider_refund_id=refund.provider_refund_id,
            amount_kopecks=refund.amount_kopecks,
            currency=refund.currency,
            status=refund.status,
            created_at=refund.created_at,
        )
        node.save()
        return self._to_domain(node)

    def save(self, refund: Refund) -> Refund:
        node = RefundNode.nodes.get(uid=refund.uid)
        node.payment_uid = refund.payment_uid
        node.provider_refund_id = refund.provider_refund_id
        node.amount_kopecks = refund.amount_kopecks
        node.currency = refund.currency
        node.status = refund.status
        node.save()
        return self._to_domain(node)

    def get_by_payment_uid(self, payment_uid: str) -> List[Refund]:
        nodes = RefundNode.nodes.filter(payment_uid=payment_uid).order_by("-created_at")
        return [self._to_domain(node) for node in nodes]

    def get_by_provider_refund_id(self, provider_refund_id: str) -> Optional[Refund]:
        nodes = list(
            RefundNode.nodes.filter(provider_refund_id=provider_refund_id)
        )
        return self._to_domain(nodes[0]) if nodes else None

    @staticmethod
    def _to_domain(node: RefundNode) -> Refund:
        return Refund(
            uid=node.uid,
            payment_uid=node.payment_uid,
            provider_refund_id=node.provider_refund_id,
            amount_kopecks=node.amount_kopecks,
            currency=node.currency,
            status=node.status,
            created_at=node.created_at,
        )

"""
Layer: Interface Adapters
Package: adapters.repositories.payment_event_repository
Responsibility: Репозиторий событий провайдера (PaymentEvent) на neomodel.
"""
from typing import Optional

from domain.models import PaymentEvent
from infrastructure.neo4j_models import PaymentEventNode


class PaymentEventRepository:
    def get_by_external_event_id(self, external_event_id: str) -> Optional[PaymentEvent]:
        node = PaymentEventNode.nodes.get_or_none(external_event_id=external_event_id)
        return self._to_domain(node) if node else None

    def save(self, event: PaymentEvent) -> PaymentEvent:
        node = PaymentEventNode.nodes.get_or_none(uid=event.uid)
        if node is None:
            node = PaymentEventNode(uid=event.uid)
        node.provider = event.provider
        node.external_event_id = event.external_event_id
        node.event_type = event.event_type
        node.payload = event.payload
        node.created_at = event.created_at
        node.processed_at = event.processed_at
        node.save()
        return self._to_domain(node)

    @staticmethod
    def _to_domain(node: PaymentEventNode) -> PaymentEvent:
        return PaymentEvent(
            uid=node.uid,
            provider=node.provider,
            external_event_id=node.external_event_id,
            event_type=node.event_type,
            payload=node.payload,
            created_at=node.created_at,
            processed_at=node.processed_at,
        )

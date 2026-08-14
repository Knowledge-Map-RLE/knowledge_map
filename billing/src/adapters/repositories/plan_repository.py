"""
Layer: Interface Adapters
Package: adapters.repositories.plan_repository
Responsibility: Репозиторий тарифов (Plan) на neomodel.
"""
from typing import List, Optional

from domain.models import Plan
from infrastructure.neo4j_models import PlanNode


class PlanRepository:
    def list_active(self) -> List[Plan]:
        nodes = PlanNode.nodes.filter(is_active=True).order_by("sort_order")
        return [self._to_domain(node) for node in nodes]

    def get_by_code(self, code: str) -> Optional[Plan]:
        node = PlanNode.nodes.get_or_none(code=code)
        return self._to_domain(node) if node else None

    @staticmethod
    def _to_domain(node: PlanNode) -> Plan:
        return Plan(
            code=node.code,
            name=node.name,
            price_kopecks=node.price_kopecks,
            currency=node.currency,
            period=node.period,
            credit_limit=node.credit_limit,
            sort_order=node.sort_order,
            is_active=node.is_active,
        )

"""
Layer: Frameworks & Drivers — Infrastructure
Package: infrastructure.seeding
Responsibility: Сид тарифов в Neo4j при старте (MERGE по коду).
"""
import logging

from infrastructure.neo4j_models import PlanNode

logger = logging.getLogger(__name__)

DEFAULT_PLANS = [
    {
        "code": "FREE",
        "name": "Free",
        "price_kopecks": 0,
        "credit_limit": 100,
        "sort_order": 0,
    },
    {
        "code": "PRO",
        "name": "Pro",
        "price_kopecks": 150000,
        "credit_limit": 10000,
        "sort_order": 1,
    },
    {
        "code": "MAX",
        "name": "Max",
        "price_kopecks": 2000000,
        "credit_limit": 200000,
        "sort_order": 2,
    },
]


def seed_plans() -> None:
    """Создаёт/обновляет тарифы FREE/PRO/MAX (идемпотентно)."""
    for item in DEFAULT_PLANS:
        node = PlanNode.nodes.get_or_none(code=item["code"])
        if node is None:
            node = PlanNode(code=item["code"])
        node.name = item["name"]
        node.price_kopecks = item["price_kopecks"]
        node.credit_limit = item["credit_limit"]
        node.sort_order = item["sort_order"]
        node.is_active = True
        node.currency = "RUB"
        node.period = "month"
        node.save()
    logger.info("Plans seeded: %s", ", ".join(p["code"] for p in DEFAULT_PLANS))

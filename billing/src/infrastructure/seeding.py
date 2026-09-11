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
        "tokens_granted": 0,
        "sort_order": 0,
    },
    {
        "code": "TOKENS_50M",
        "name": "50M токенов",
        "price_kopecks": 200000,
        "tokens_granted": 50_000_000,
        "sort_order": 1,
    },
    {
        "code": "TOKENS_200M",
        "name": "200M токенов",
        "price_kopecks": 800000,
        "tokens_granted": 200_000_000,
        "sort_order": 2,
    },
]


def seed_plans() -> None:
    """Создаёт/обновляет тарифы (идемпотентно)."""
    for item in DEFAULT_PLANS:
        node = PlanNode.nodes.get_or_none(code=item["code"])
        if node is None:
            node = PlanNode(code=item["code"])
        node.name = item["name"]
        node.price_kopecks = item["price_kopecks"]
        node.tokens_granted = item["tokens_granted"]
        node.sort_order = item["sort_order"]
        node.is_active = True
        node.currency = "RUB"
        node.period = "token"
        node.save()
    logger.info("Plans seeded: %s", ", ".join(p["code"] for p in DEFAULT_PLANS))

"""
Layer: Interface Adapters — Repository
Package: adapters.repositories.financial_plan_repository
Responsibility: neomodel-реализация репозитория финансовых планов.

Принадлежит слою Interface Adapters, потому что транслирует между
доменным языком (domain.models.admin.FinancialPlan) и ORM-деталями
(neomodel FinancialPlanNode).
Знает о neomodel, но application-слой — нет.

Поле данных плана хранится в Neo4j как JSON-строка (data_json)
и сериализуется/десериализуется через модуль json.
При создании нового плана предыдущий активный автоматически
деактивируется (создать можно только один активный план).

Класс реализует интерфейс репозитория без наследования от Protocol
(structural subtyping).

Allowed imports: neomodel, infrastructure.neo4j.admin_models, domain.models.*, domain.exceptions
Forbidden imports: fastapi, web, grpc, aioboto3
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import List, Optional

from neomodel import db, DoesNotExist

from infrastructure.neo4j.admin_models import FinancialPlanNode
from domain.models.admin import FinancialPlan

logger = logging.getLogger(__name__)


def _serialize_data(data: dict) -> str:
    """Сериализует плановые метрики в JSON-строку для Neo4j."""
    return json.dumps(data or {}, ensure_ascii=False)


def _parse_data(data_json: str) -> dict:
    """Десериализует JSON-строку из Neo4j в dict."""
    try:
        return json.loads(data_json or "{}")
    except (ValueError, TypeError):
        logger.warning("Невалидный JSON в data_json финансового плана")
        return {}


def _orm_to_domain(orm_plan: FinancialPlanNode) -> FinancialPlan:
    """Транслирует ORM-объект FinancialPlanNode в доменный dataclass."""
    return FinancialPlan(
        uid=orm_plan.uid,
        version=orm_plan.version or 1,
        name=orm_plan.name,
        data=_parse_data(orm_plan.data_json),
        is_active=orm_plan.is_active or False,
        created_by_uid=orm_plan.created_by_uid,
        created_at=orm_plan.created_at.isoformat(),
        updated_at=orm_plan.updated_at.isoformat(),
    )


class FinancialPlanRepository:
    """
    neomodel-реализация репозитория финансовых планов.
    Реализует интерфейс репозитория (structural subtyping).
    """

    def _next_version(self) -> int:
        """Вычисляет следующий номер версии плана (max + 1)."""
        query = "MATCH (p:FinancialPlan) RETURN coalesce(max(p.version), 0)"
        result, _ = db.cypher_query(query)
        max_version = int(result[0][0]) if result and result[0][0] is not None else 0
        return max_version + 1

    def create(self, data: dict) -> FinancialPlan:
        """Создаёт финансовый план, деактивируя предыдущий активный."""
        with db.transaction:
            for plan in FinancialPlanNode.nodes.filter(is_active=True):
                plan.is_active = False
                plan.updated_at = datetime.utcnow()
                plan.save()
                logger.info("Финансовый план '%s' деактивирован", plan.uid)

            version = int(data.get("version") or 0)
            if version <= 0:
                version = self._next_version()

            orm_plan = FinancialPlanNode(
                version=version,
                name=str(data["name"]),
                data_json=_serialize_data(data.get("data", {})),
                is_active=True,
                created_by_uid=str(data["created_by_uid"]),
            )
            orm_plan.save()
            orm_plan.refresh()
            logger.info(
                "Создан финансовый план '%s' (версия %d)", orm_plan.uid, orm_plan.version
            )
            return _orm_to_domain(orm_plan)

    def get_active(self) -> Optional[FinancialPlan]:
        """Возвращает текущий активный план или None."""
        plan = (
            FinancialPlanNode.nodes.filter(is_active=True).order_by("-version").first()
        )
        return _orm_to_domain(plan) if plan else None

    def get_by_uid(self, uid: str) -> Optional[FinancialPlan]:
        """Возвращает план по uid или None."""
        try:
            orm_plan = FinancialPlanNode.nodes.get(uid=uid)
            return _orm_to_domain(orm_plan)
        except DoesNotExist:
            return None

    def get_all(self) -> List[FinancialPlan]:
        """Возвращает все финансовые планы (новые версии первыми)."""
        plans = FinancialPlanNode.nodes.order_by("-version", "-created_at")
        return [_orm_to_domain(p) for p in plans]

    def update(self, uid: str, data: dict) -> Optional[FinancialPlan]:
        """Обновляет данные плана. Возвращает None, если план не найден."""
        with db.transaction:
            try:
                orm_plan = FinancialPlanNode.nodes.get(uid=uid)
            except DoesNotExist:
                return None

            if "name" in data:
                orm_plan.name = str(data["name"])
            if "data" in data:
                orm_plan.data_json = _serialize_data(data["data"])
            if "version" in data:
                orm_plan.version = int(data["version"])
            if "is_active" in data:
                orm_plan.is_active = bool(data["is_active"])

            orm_plan.updated_at = datetime.utcnow()
            orm_plan.save()
            orm_plan.refresh()
            logger.info("Финансовый план '%s' обновлён", orm_plan.uid)
            return _orm_to_domain(orm_plan)

    def deactivate(self, uid: str) -> bool:
        """Деактивирует план. Возвращает False, если план не найден."""
        with db.transaction:
            try:
                orm_plan = FinancialPlanNode.nodes.get(uid=uid)
            except DoesNotExist:
                return False

            orm_plan.is_active = False
            orm_plan.updated_at = datetime.utcnow()
            orm_plan.save()
            logger.info("Финансовый план '%s' деактивирован", uid)
            return True
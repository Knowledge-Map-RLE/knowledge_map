"""
Layer: Interface Adapters — Repository
Package: adapters.repositories.expense_repository
Responsibility: neomodel-реализация репозитория расходов.

Принадлежит слою Interface Adapters, потому что транслирует между
доменным языком (domain.models.admin.Expense, ExpenseSummary) и
ORM-деталями (neomodel ExpenseNode).
Знает о neomodel, но application-слой — нет.

Агрегация расходов по категориям выполняется одним Cypher-запросом
через from neomodel import db.
Класс реализует интерфейс репозитория без наследования от Protocol
(structural subtyping).

Allowed imports: neomodel, infrastructure.neo4j.admin_models, domain.models.*, domain.exceptions
Forbidden imports: fastapi, web, grpc, aioboto3
"""
from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, List, Optional

from neomodel import db, DoesNotExist

from infrastructure.neo4j.admin_models import ExpenseNode
from domain.models.admin import Expense, ExpenseSummary

logger = logging.getLogger(__name__)


def _parse_datetime(value: Any) -> datetime:
    """Преобразует ISO-строку или datetime в datetime для neomodel."""
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _kopecks_to_rubles(kopecks: Any) -> Decimal:
    """Переводит копейки (int) в рубли (Decimal)."""
    return Decimal(str(kopecks or 0)) / Decimal("100")


def _orm_to_domain(orm_expense: ExpenseNode) -> Expense:
    """Транслирует ORM-объект ExpenseNode в доменный dataclass."""
    return Expense(
        uid=orm_expense.uid,
        category=orm_expense.category,
        subcategory=orm_expense.subcategory or "",
        description=orm_expense.description,
        amount_kopecks=orm_expense.amount_kopecks,
        currency=orm_expense.currency or "RUB",
        period_start=orm_expense.period_start.isoformat(),
        period_end=orm_expense.period_end.isoformat(),
        is_recurring=orm_expense.is_recurring or False,
        is_fixed=orm_expense.is_fixed or False,
        source=orm_expense.source or "manual",
        created_by_uid=orm_expense.created_by_uid,
        created_at=orm_expense.created_at.isoformat(),
        updated_at=orm_expense.updated_at.isoformat(),
    )


class ExpenseRepository:
    """
    neomodel-реализация репозитория расходов.
    Реализует интерфейс репозитория (structural subtyping).
    """

    def create(self, data: dict) -> Expense:
        """Создаёт расход и возвращает доменный Expense."""
        with db.transaction:
            orm_expense = ExpenseNode(
                category=str(data["category"]),
                subcategory=str(data.get("subcategory", "")),
                description=str(data["description"]),
                amount_kopecks=int(data["amount_kopecks"]),
                currency=str(data.get("currency", "RUB")),
                period_start=_parse_datetime(data["period_start"]),
                period_end=_parse_datetime(data["period_end"]),
                is_recurring=bool(data.get("is_recurring", False)),
                is_fixed=bool(data.get("is_fixed", False)),
                source=str(data.get("source", "manual")),
                created_by_uid=str(data["created_by_uid"]),
            )
            orm_expense.save()
            orm_expense.refresh()
            logger.info("Расход '%s' создан (%s)", orm_expense.uid, orm_expense.category)
            return _orm_to_domain(orm_expense)

    def get_by_uid(self, uid: str) -> Optional[Expense]:
        """Возвращает расход по uid или None."""
        try:
            orm_expense = ExpenseNode.nodes.get(uid=uid)
            return _orm_to_domain(orm_expense)
        except DoesNotExist:
            return None

    def get_all(self, filters: dict = None) -> List[Expense]:
        """Возвращает все расходы, опционально отфильтрованные.

        Поддерживаемые фильтры: category, is_fixed, period_start, period_end.
        """
        filters = filters or {}
        nodeset = ExpenseNode.nodes

        if filters.get("category"):
            nodeset = nodeset.filter(category=str(filters["category"]))
        if filters.get("is_fixed") is not None:
            nodeset = nodeset.filter(is_fixed=bool(filters["is_fixed"]))
        if filters.get("period_start"):
            nodeset = nodeset.filter(
                period_start__gte=_parse_datetime(filters["period_start"])
            )
        if filters.get("period_end"):
            nodeset = nodeset.filter(
                period_end__lte=_parse_datetime(filters["period_end"])
            )

        return [
            _orm_to_domain(e)
            for e in nodeset.order_by("-period_start", "-created_at")
        ]

    def update(self, uid: str, data: dict) -> Optional[Expense]:
        """Обновляет поля расхода. Возвращает None, если расход не найден."""
        with db.transaction:
            try:
                orm_expense = ExpenseNode.nodes.get(uid=uid)
            except DoesNotExist:
                return None

            if "category" in data:
                orm_expense.category = str(data["category"])
            if "subcategory" in data:
                orm_expense.subcategory = str(data["subcategory"])
            if "description" in data:
                orm_expense.description = str(data["description"])
            if "amount_kopecks" in data:
                orm_expense.amount_kopecks = int(data["amount_kopecks"])
            if "currency" in data:
                orm_expense.currency = str(data["currency"])
            if "period_start" in data:
                orm_expense.period_start = _parse_datetime(data["period_start"])
            if "period_end" in data:
                orm_expense.period_end = _parse_datetime(data["period_end"])
            if "is_recurring" in data:
                orm_expense.is_recurring = bool(data["is_recurring"])
            if "is_fixed" in data:
                orm_expense.is_fixed = bool(data["is_fixed"])
            if "source" in data:
                orm_expense.source = str(data["source"])

            orm_expense.updated_at = datetime.utcnow()
            orm_expense.save()
            orm_expense.refresh()
            logger.info("Расход '%s' обновлён", orm_expense.uid)
            return _orm_to_domain(orm_expense)

    def delete(self, uid: str) -> bool:
        """Удаляет расход. Возвращает False, если расход не найден."""
        with db.transaction:
            try:
                orm_expense = ExpenseNode.nodes.get(uid=uid)
            except DoesNotExist:
                return False

            orm_expense.delete()
            logger.info("Расход '%s' удалён", uid)
            return True

    def get_summary(self) -> ExpenseSummary:
        """Агрегирует все расходы по категориям и типу (fixed/variable).

        Категории: infrastructure | ai_tokens | acquiring | advertising | tax | other.
        Суммы возвращаются в рублях (Decimal).
        """
        query = (
            "MATCH (e:Expense) "
            "RETURN "
            "  coalesce(sum(e.amount_kopecks), 0) AS total_kopecks, "
            "  coalesce(sum(CASE WHEN e.category = 'infrastructure' THEN e.amount_kopecks ELSE 0 END), 0) AS infrastructure_kopecks, "  # noqa: E501
            "  coalesce(sum(CASE WHEN e.category = 'ai_tokens' THEN e.amount_kopecks ELSE 0 END), 0) AS ai_tokens_kopecks, "  # noqa: E501
            "  coalesce(sum(CASE WHEN e.category = 'acquiring' THEN e.amount_kopecks ELSE 0 END), 0) AS acquiring_kopecks, "  # noqa: E501
            "  coalesce(sum(CASE WHEN e.category = 'advertising' THEN e.amount_kopecks ELSE 0 END), 0) AS advertising_kopecks, "  # noqa: E501
            "  coalesce(sum(CASE WHEN e.category = 'tax' THEN e.amount_kopecks ELSE 0 END), 0) AS tax_kopecks, "
            "  coalesce(sum(CASE WHEN e.category = 'other' THEN e.amount_kopecks ELSE 0 END), 0) AS other_kopecks, "
            "  coalesce(sum(CASE WHEN e.is_fixed = true THEN e.amount_kopecks ELSE 0 END), 0) AS fixed_kopecks, "
            "  coalesce(sum(CASE WHEN e.is_fixed = false THEN e.amount_kopecks ELSE 0 END), 0) AS variable_kopecks"
        )
        result, _ = db.cypher_query(query)
        row = result[0]

        summary = ExpenseSummary(
            total_rubles=_kopecks_to_rubles(row[0]),
            infrastructure_rubles=_kopecks_to_rubles(row[1]),
            ai_tokens_rubles=_kopecks_to_rubles(row[2]),
            acquiring_rubles=_kopecks_to_rubles(row[3]),
            advertising_rubles=_kopecks_to_rubles(row[4]),
            tax_rubles=_kopecks_to_rubles(row[5]),
            other_rubles=_kopecks_to_rubles(row[6]),
            fixed_rubles=_kopecks_to_rubles(row[7]),
            variable_rubles=_kopecks_to_rubles(row[8]),
        )
        logger.info("Сформирована сводка по расходам: %s", summary.total_rubles)
        return summary
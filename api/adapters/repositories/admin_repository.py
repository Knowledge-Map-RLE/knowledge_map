"""
Layer: Interface Adapters — Repository
Package: adapters.repositories.admin_repository
Responsibility: neomodel-реализация репозитория admin-панели экономики.

Транслирует между доменным языком (domain.models.admin) и ORM-деталями (neomodel).
Знает о neomodel, но application-слой — нет.

Удовлетворяет AdminRepositoryProtocol (application/ports/repositories.py)
без явного наследования (structural subtyping).

Allowed imports: neomodel, infrastructure.neo4j.admin_models, infrastructure.neo4j.orm_models,
                 domain.models.admin, decimal, datetime, typing
Forbidden imports: fastapi, web, grpc, aioboto3
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Optional

from neomodel import db, DoesNotExist

from infrastructure.neo4j.admin_models import (
    ExpenseNode,
    AIProviderNode,
    ProviderPriceVersionNode,
    FinancialPlanNode,
    AdminAuditLogNode,
    StrategyStageNode,
    LaunchScenarioNode,
)
from infrastructure.neo4j.orm_models import AIUsage

logger = logging.getLogger(__name__)


# =============================================================================
# Private helpers
# =============================================================================


def _safe_decimal(value: object, default: Decimal = Decimal("0")) -> Decimal:
    """Безопасное преобразование в Decimal (строки, числа, None)."""
    if value is None:
        return default
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return default


def _row_to_dict(row: tuple, columns: list[str]) -> dict:
    """Преобразует строку результата Cypher в dict по именам колонок."""
    return {col: row[i] for i, col in enumerate(columns)}


class AdminRepository:
    """
    neomodel-реализация репозитория admin-панели экономики.
    Удовлетворяет AdminRepositoryProtocol (structural subtyping).
    """

    # =========================================================================
    # Dashboard KPI
    # =========================================================================

    def get_total_users(self) -> int:
        """Количество всех :User в кластере Neo4j (узлы живут в auth-service)."""
        query = "MATCH (u:User) RETURN count(u) AS cnt"
        result, _ = db.cypher_query(query)
        return int(result[0][0]) if result else 0

    def get_paying_users(self) -> int:
        """Количество уникальных пользователей с ACTIVE-подпиской."""
        query = (
            "MATCH (s:Subscription) "
            "WHERE s.status = 'ACTIVE' "
            "RETURN count(DISTINCT s.user_id) AS cnt"
        )
        result, _ = db.cypher_query(query)
        return int(result[0][0]) if result else 0

    def get_active_users(self, period_days: int) -> int:
        """Количество пользователей с AIUsage за последние N дней."""
        cutoff = (datetime.utcnow() - timedelta(days=period_days)).isoformat()
        query = (
            "MATCH (u:AIUsage) "
            "WHERE u.created_at >= $cutoff "
            "RETURN count(DISTINCT u.user_uid) AS cnt"
        )
        result, _ = db.cypher_query(query, {"cutoff": cutoff})
        return int(result[0][0]) if result else 0

    # =========================================================================
    # AI Usage агрегаты
    # =========================================================================

    def get_user_ai_usage_aggregates(self, user_uid: str) -> dict:
        """Агрегированная статистика AIUsage для одного пользователя."""
        query = (
            "MATCH (u:AIUsage {user_uid: $uid}) "
            "RETURN "
            "  sum(u.actual_input_tokens) AS input_tokens, "
            "  sum(u.actual_output_tokens) AS output_tokens, "
            "  sum(u.actual_cached_tokens) AS cached_tokens, "
            "  u.actual_cost AS cost_rows, "
            "  count(*) AS request_count, "
            "  max(u.created_at) AS last_request"
        )
        result, _ = db.cypher_query(query, {"uid": user_uid})
        if not result:
            return {
                "user_uid": user_uid,
                "input_tokens": 0,
                "output_tokens": 0,
                "cached_tokens": 0,
                "total_tokens": 0,
                "ai_cost": Decimal("0"),
                "request_count": 0,
                "last_request": None,
            }

        row = result[0]
        # cost_rows — это не скаляр, а все значения actual_cost.
        # Cypher sum() не работает для строк — собираем в Python.
        cost_query = (
            "MATCH (u:AIUsage {user_uid: $uid}) "
            "RETURN u.actual_cost AS cost"
        )
        cost_rows, _ = db.cypher_query(cost_query, {"uid": user_uid})
        total_cost = sum(_safe_decimal(r[0]) for r in cost_rows)

        input_tokens = int(row[0] or 0)
        output_tokens = int(row[1] or 0)
        cached_tokens = int(row[2] or 0)

        return {
            "user_uid": user_uid,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cached_tokens": cached_tokens,
            "total_tokens": input_tokens + output_tokens + cached_tokens,
            "ai_cost": total_cost,
            "request_count": int(row[4] or 0),
            "last_request": str(row[5]) if row[5] else None,
        }

    def get_all_users_usage_aggregates(self, period_days: int) -> list[dict]:
        """Агрегация AIUsage по всем пользователям за период."""
        cutoff = (datetime.utcnow() - timedelta(days=period_days)).isoformat()
        query = (
            "MATCH (u:AIUsage) "
            "WHERE u.created_at >= $cutoff "
            "WITH u "
            "RETURN "
            "  u.user_uid AS user_uid, "
            "  sum(u.actual_input_tokens) AS input_tokens, "
            "  sum(u.actual_output_tokens) AS output_tokens, "
            "  sum(u.actual_cached_tokens) AS cached_tokens, "
            "  count(*) AS request_count, "
            "  max(u.created_at) AS last_request "
            "ORDER BY input_tokens + output_tokens + cached_tokens DESC"
        )
        result, _ = db.cypher_query(query, {"cutoff": cutoff})

        if not result:
            return []

        # Собираем стоимость отдельно для каждого user_uid
        user_uids = [str(r[0]) for r in result]
        cost_map: dict[str, Decimal] = {uid: Decimal("0") for uid in user_uids}
        if user_uids:
            cost_query = (
                "MATCH (u:AIUsage) "
                "WHERE u.user_uid IN $uids AND u.created_at >= $cutoff "
                "RETURN u.user_uid AS uid, u.actual_cost AS cost"
            )
            cost_rows, _ = db.cypher_query(
                cost_query, {"uids": user_uids, "cutoff": cutoff}
            )
            for row in cost_rows:
                uid = str(row[0])
                cost_map[uid] = cost_map.get(uid, Decimal("0")) + _safe_decimal(row[1])

        aggregates = []
        for row in result:
            uid = str(row[0])
            input_tokens = int(row[1] or 0)
            output_tokens = int(row[2] or 0)
            cached_tokens = int(row[3] or 0)
            aggregates.append({
                "user_uid": uid,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cached_tokens": cached_tokens,
                "total_tokens": input_tokens + output_tokens + cached_tokens,
                "ai_cost": cost_map.get(uid, Decimal("0")),
                "request_count": int(row[4] or 0),
                "last_request": str(row[5]) if row[5] else None,
            })

        return aggregates

    # =========================================================================
    # Токены и аномалии
    # =========================================================================

    def get_token_percentiles(self) -> dict:
        """Перцентили (P50, P90, P95, P99) суммарных токенов на пользователя."""
        query = (
            "MATCH (u:AIUsage) "
            "WITH u.user_uid AS uid, "
            "     sum(u.actual_input_tokens + u.actual_output_tokens + u.actual_cached_tokens) AS total "
            "RETURN total "
            "ORDER BY total"
        )
        result, _ = db.cypher_query(query)
        if not result:
            return {"p50": 0, "p90": 0, "p95": 0, "p99": 0, "avg": 0}

        totals = sorted([int(r[0] or 0) for r in result])
        n = len(totals)
        avg = sum(totals) / n if n else 0

        def _percentile(data: list[int], p: float) -> int:
            idx = int(len(data) * p / 100)
            idx = min(idx, len(data) - 1)
            return data[idx]

        return {
            "p50": _percentile(totals, 50),
            "p90": _percentile(totals, 90),
            "p95": _percentile(totals, 95),
            "p99": _percentile(totals, 99),
            "avg": round(avg, 2),
        }

    def get_anomaly_users(self, z_threshold: float = 2.0) -> list[dict]:
        """Пользователи с потреблением токенов выше z-score порога."""
        query = (
            "MATCH (u:AIUsage) "
            "WITH u.user_uid AS uid, "
            "     sum(u.actual_input_tokens + u.actual_output_tokens + u.actual_cached_tokens) AS total "
            "RETURN uid, total "
            "ORDER BY total DESC"
        )
        result, _ = db.cypher_query(query)
        if not result:
            return []

        rows = [(str(r[0]), int(r[1] or 0)) for r in result]
        totals = [t for _, t in rows]
        n = len(totals)
        if n < 2:
            return []

        mean = sum(totals) / n
        variance = sum((t - mean) ** 2 for t in totals) / (n - 1)
        stddev = variance ** 0.5
        if stddev == 0:
            return []

        outliers = []
        for uid, total in rows:
            z = (total - mean) / stddev
            if z > z_threshold:
                outliers.append({"uid": uid, "total_tokens": total, "z_score": round(z, 2)})

        # Собираем стоимость для аномальных пользователей
        anomaly_uids = [o["uid"] for o in outliers]
        if anomaly_uids:
            cost_query = (
                "MATCH (u:AIUsage) "
                "WHERE u.user_uid IN $uids "
                "RETURN u.user_uid AS uid, u.actual_cost AS cost"
            )
            cost_rows, _ = db.cypher_query(cost_query, {"uids": anomaly_uids})
            cost_map: dict[str, Decimal] = {}
            for row in cost_rows:
                uid = str(row[0])
                cost_map[uid] = cost_map.get(uid, Decimal("0")) + _safe_decimal(row[1])
            for o in outliers:
                o["ai_cost"] = cost_map.get(o["uid"], Decimal("0"))
        else:
            for o in outliers:
                o["ai_cost"] = Decimal("0")

        return outliers

    # =========================================================================
    # Фильтрация пользователей
    # =========================================================================

    def get_users_with_filters(
        self, filters: dict, offset: int, limit: int
    ) -> tuple[list[dict], int]:
        """Постраничный список пользователей с фильтрами.

        Поддерживаемые фильтры:
            plan_code: str — код пакета из Subscription
            has_payments: bool — есть ли успешные платежи
            min_tokens / max_tokens: int — диапазон суммарных токенов
            has_activity: bool — есть ли AIUsage за последние 30 дней
        """
        # Шаг 1: агрегация AIUsage по пользователям
        usage_query = (
            "MATCH (u:AIUsage) "
            "WITH u.user_uid AS uid, "
            "  sum(u.actual_input_tokens) AS input_tokens, "
            "  sum(u.actual_output_tokens) AS output_tokens, "
            "  sum(u.actual_cached_tokens) AS cached_tokens, "
            "  count(*) AS request_count, "
            "  max(u.created_at) AS last_request "
            "RETURN uid, input_tokens, output_tokens, cached_tokens, "
            "       input_tokens + output_tokens + cached_tokens AS total_tokens, "
            "       request_count, last_request"
        )
        usage_rows, _ = db.cypher_query(usage_query)
        usage_map: dict[str, dict] = {}
        for row in usage_rows:
            uid = str(row[0])
            usage_map[uid] = {
                "input_tokens": int(row[1] or 0),
                "output_tokens": int(row[2] or 0),
                "cached_tokens": int(row[3] or 0),
                "total_tokens": int(row[4] or 0),
                "request_count": int(row[5] or 0),
                "last_request": str(row[6]) if row[6] else None,
            }

        # Шаг 2: стоимость по пользователям
        all_uids = list(usage_map.keys())
        cost_map: dict[str, Decimal] = {}
        if all_uids:
            cost_query = (
                "MATCH (u:AIUsage) "
                "WHERE u.user_uid IN $uids "
                "RETURN u.user_uid AS uid, u.actual_cost AS cost"
            )
            cost_rows, _ = db.cypher_query(cost_query, {"uids": all_uids})
            for row in cost_rows:
                uid = str(row[0])
                cost_map[uid] = cost_map.get(uid, Decimal("0")) + _safe_decimal(row[1])

        # Шаг 3: подписки
        sub_query = (
            "MATCH (s:Subscription) "
            "RETURN s.user_id AS uid, s.plan_code AS plan_code, s.status AS status"
        )
        sub_rows, _ = db.cypher_query(sub_query)
        sub_map: dict[str, dict] = {}
        for row in sub_rows:
            uid = str(row[0])
            sub_map[uid] = {
                "plan_code": str(row[1] or ""),
                "status": str(row[2] or ""),
            }

        # Шаг 4: платежи
        payment_query = (
            "MATCH (p:Payment) "
            "WHERE p.status = 'SUCCEEDED' "
            "RETURN p.user_id AS uid, count(*) AS pay_count, "
            "       sum(p.amount_kopecks) AS total_kopecks"
        )
        pay_rows, _ = db.cypher_query(payment_query)
        pay_map: dict[str, dict] = {}
        for row in pay_rows:
            uid = str(row[0])
            pay_map[uid] = {
                "payment_count": int(row[1] or 0),
                "total_kopecks": int(row[2] or 0),
            }

        # Шаг 5: активность за 30 дней
        active_users: set[str] = set()
        if filters.get("has_activity") is not None:
            cutoff_30 = (datetime.utcnow() - timedelta(days=30)).isoformat()
            activity_query = (
                "MATCH (u:AIUsage) "
                "WHERE u.created_at >= $cutoff "
                "RETURN DISTINCT u.user_uid AS uid"
            )
            act_rows, _ = db.cypher_query(activity_query, {"cutoff": cutoff_30})
            active_users = {str(r[0]) for r in act_rows}

        # Шаг 6: собираем и фильтруем
        all_user_uids = set(usage_map.keys()) | set(sub_map.keys()) | set(pay_map.keys())
        enriched: list[dict] = []

        for uid in all_user_uids:
            usage = usage_map.get(uid, {
                "input_tokens": 0, "output_tokens": 0, "cached_tokens": 0,
                "total_tokens": 0, "request_count": 0, "last_request": None,
            })
            sub = sub_map.get(uid, {"plan_code": "", "status": ""})
            pay = pay_map.get(uid, {"payment_count": 0, "total_kopecks": 0})
            cost = cost_map.get(uid, Decimal("0"))

            # Фильтры
            plan_code = filters.get("plan_code")
            if plan_code and sub["plan_code"] != plan_code:
                continue

            has_payments = filters.get("has_payments")
            if has_payments is True and pay["payment_count"] == 0:
                continue
            if has_payments is False and pay["payment_count"] > 0:
                continue

            min_tokens = filters.get("min_tokens")
            if min_tokens is not None and usage["total_tokens"] < min_tokens:
                continue
            max_tokens = filters.get("max_tokens")
            if max_tokens is not None and usage["total_tokens"] > max_tokens:
                continue

            has_activity = filters.get("has_activity")
            if has_activity is True and uid not in active_users:
                continue
            if has_activity is False and uid in active_users:
                continue

            enriched.append({
                "user_uid": uid,
                "plan_code": sub["plan_code"],
                "subscription_status": sub["status"],
                "payment_count": pay["payment_count"],
                "total_kopecks": pay["total_kopecks"],
                "input_tokens": usage["input_tokens"],
                "output_tokens": usage["output_tokens"],
                "cached_tokens": usage["cached_tokens"],
                "total_tokens": usage["total_tokens"],
                "ai_cost": cost,
                "request_count": usage["request_count"],
                "last_request": usage["last_request"],
            })

        total_count = len(enriched)

        # Сортировка по total_tokens DESC, пагинация
        enriched.sort(key=lambda x: x["total_tokens"], reverse=True)
        page = enriched[offset : offset + limit]

        return page, total_count

    # =========================================================================
    # Выручка и AI-cost по периодам
    # =========================================================================

    def get_revenue_by_period(
        self, period: str, start_date: str, end_date: str
    ) -> list[dict]:
        """Агрегация успешных платежей по временному периоду."""
        trunc_expr = self._date_trunc_cypher(period, alias="p")

        query = (
            "MATCH (p:Payment) "
            "WHERE p.status = 'SUCCEEDED' "
            "  AND p.created_at >= $start "
            "  AND p.created_at < $end "
            f"RETURN {trunc_expr} AS period, "
            "       count(*) AS sale_count, "
            "       sum(p.amount_kopecks) AS total_kopecks "
            "ORDER BY period"
        )
        result, _ = db.cypher_query(query, {"start": start_date, "end": end_date})

        return [
            {
                "period": str(r[0]),
                "sale_count": int(r[1] or 0),
                "total_kopecks": int(r[2] or 0),
                "revenue_rubles": Decimal(str(int(r[2] or 0))) / Decimal("100"),
            }
            for r in result
        ]

    def get_ai_cost_by_period(
        self, period: str, start_date: str, end_date: str
    ) -> list[dict]:
        """Агрегация AIUsage actual_cost по временному периоду."""
        trunc_expr = self._date_trunc_cypher(period, alias="u")

        # Собираем все строки за период, группируем в Python
        query = (
            "MATCH (u:AIUsage) "
            "WHERE u.created_at >= $start AND u.created_at < $end "
            f"RETURN {trunc_expr} AS period, u.actual_cost AS cost "
            "ORDER BY period"
        )
        result, _ = db.cypher_query(query, {"start": start_date, "end": end_date})

        period_map: dict[str, Decimal] = {}
        for row in result:
            period_key = str(row[0])
            period_map[period_key] = period_map.get(
                period_key, Decimal("0")
            ) + _safe_decimal(row[1])

        return [
            {"period": k, "ai_cost_rubles": v}
            for k, v in sorted(period_map.items())
        ]

    # =========================================================================
    # Продажи
    # =========================================================================

    def get_sales_by_plan(self) -> list[dict]:
        """Агрегация успешных платежей по plan_code."""
        query = (
            "MATCH (p:Payment) "
            "WHERE p.status = 'SUCCEEDED' "
            "RETURN p.plan_code AS plan_code, "
            "       count(*) AS sale_count, "
            "       sum(p.amount_kopecks) AS total_kopecks "
            "ORDER BY total_kopecks DESC"
        )
        result, _ = db.cypher_query(query)

        return [
            {
                "plan_code": str(r[0] or ""),
                "sale_count": int(r[1] or 0),
                "total_kopecks": int(r[2] or 0),
                "revenue_rubles": Decimal(str(int(r[2] or 0))) / Decimal("100"),
            }
            for r in result
        ]

    def get_total_sales_stats(self) -> dict:
        """Суммарная статистика продаж и возвратов."""
        sales_query = (
            "MATCH (p:Payment) "
            "WHERE p.status = 'SUCCEEDED' "
            "RETURN count(*) AS cnt, "
            "       sum(p.amount_kopecks) AS total_kopecks"
        )
        sales_result, _ = db.cypher_query(sales_query)
        sales_row = sales_result[0] if sales_result else (0, 0)
        sales_count = int(sales_row[0] or 0)
        total_kopecks = int(sales_row[1] or 0)

        refund_query = (
            "MATCH (r:Refund) "
            "WHERE r.status = 'SUCCEEDED' "
            "RETURN count(*) AS cnt, "
            "       sum(r.amount_kopecks) AS total_kopecks"
        )
        refund_result, _ = db.cypher_query(refund_query)
        refund_row = refund_result[0] if refund_result else (0, 0)
        refund_count = int(refund_row[0] or 0)
        refund_kopecks = int(refund_row[1] or 0)

        revenue_rubles = Decimal(str(total_kopecks)) / Decimal("100")
        refund_rubles = Decimal(str(refund_kopecks)) / Decimal("100")
        net_rubles = revenue_rubles - refund_rubles
        avg_check = (
            revenue_rubles / Decimal(str(sales_count)) if sales_count else Decimal("0")
        )

        return {
            "total_sales_count": sales_count,
            "total_revenue_kopecks": total_kopecks,
            "total_revenue_rubles": revenue_rubles,
            "average_check_rubles": avg_check,
            "refunds_count": refund_count,
            "refunds_amount_kopecks": refund_kopecks,
            "refunds_amount_rubles": refund_rubles,
            "net_revenue_rubles": net_rubles,
        }

    # =========================================================================
    # Приватные утилиты
    # =========================================================================

    @staticmethod
    def _date_trunc_cypher(period: str, alias: str = "u") -> str:
        """Возвращает Cypher-выражение для группировки по периоду.

        ``alias`` — алиас узла в Cypher (``u`` для AIUsage, ``p`` для Payment).
        Использует apoc.temporal.format, если APOC доступен.
        Иначе — строковое срезание даты из ISO-формата.
        """
        if period == "day":
            return f"substring(tostring({alias}.created_at), 0, 10)"
        elif period == "week":
            return f"substring(tostring({alias}.created_at), 0, 10)"
        elif period == "month":
            return f"substring(tostring({alias}.created_at), 0, 7)"
        else:
            # По умолчанию — месяц
            return f"substring(tostring({alias}.created_at), 0, 7)"

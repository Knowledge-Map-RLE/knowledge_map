"""
Layer: Frameworks & Drivers — Web
Package: web.routers.admin.users
Responsibility: HTTP-контроллеры управления пользователями в admin-панели.

Allowed imports: fastapi, web.dependencies, adapters.repositories.admin_repository
Forbidden imports: neomodel, services
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from adapters.repositories.admin_repository import AdminRepository
from web.dependencies import get_current_admin

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/")
async def list_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: Optional[str] = Query(default=None),
    plan_code: Optional[str] = Query(default=None),
    has_payments: Optional[bool] = Query(default=None),
    min_tokens: Optional[int] = Query(default=None),
    max_tokens: Optional[int] = Query(default=None),
    is_active: Optional[bool] = Query(default=None),
    min_cost: Optional[float] = Query(default=None),
    max_cost: Optional[float] = Query(default=None),
    admin: dict = Depends(get_current_admin),
):
    """Список пользователей с пагинацией и фильтрами."""
    repo = AdminRepository()

    filters: dict = {}
    if plan_code:
        filters["plan_code"] = plan_code
    if has_payments is not None:
        filters["has_payments"] = has_payments
    if min_tokens is not None:
        filters["min_tokens"] = min_tokens
    if max_tokens is not None:
        filters["max_tokens"] = max_tokens

    offset = (page - 1) * page_size
    users, total = repo.get_users_with_filters(filters=filters, offset=offset, limit=page_size)

    result_users = []
    for u in users:
        item = {
            "uid": u["user_uid"],
            "plan_code": u["plan_code"],
            "subscription_status": u["subscription_status"],
            "payment_count": u["payment_count"],
            "total_payments_rubles": float(u["total_kopecks"]) / 100.0,
            "input_tokens": u["input_tokens"],
            "output_tokens": u["output_tokens"],
            "cached_tokens": u["cached_tokens"],
            "total_tokens": u["total_tokens"],
            "ai_cost_rubles": float(u["ai_cost"]),
            "request_count": u["request_count"],
            "last_request": u["last_request"],
        }

        if min_cost is not None and item["ai_cost_rubles"] < min_cost:
            continue
        if max_cost is not None and item["ai_cost_rubles"] > max_cost:
            continue

        result_users.append(item)

    if search:
        search_lower = search.lower()
        result_users = [u for u in result_users if search_lower in u["uid"].lower()]

    logger.info("Users list: total=%d, page=%d, page_size=%d", total, page, page_size)

    return {
        "users": result_users,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/{uid}")
async def get_user_detail(
    uid: str,
    admin: dict = Depends(get_current_admin),
):
    """Подробная карточка пользователя со всеми финансовыми метриками."""
    repo = AdminRepository()
    usage = repo.get_user_ai_usage_aggregates(uid)

    if usage["request_count"] == 0 and usage["total_tokens"] == 0:
        raise HTTPException(status_code=404, detail=f"Пользователь {uid} не найден или нет данных AIUsage")

    from neomodel import db

    sub_query = (
        "MATCH (s:Subscription {user_id: $uid}) "
        "RETURN s.plan_code AS plan_code, s.status AS status"
    )
    sub_result, _ = db.cypher_query(sub_query, {"uid": uid})
    plan_code = str(sub_result[0][0]) if sub_result else ""
    sub_status = str(sub_result[0][1]) if sub_result else ""

    pay_query = (
        "MATCH (p:Payment {user_id: $uid}) "
        "WHERE p.status = 'SUCCEEDED' "
        "RETURN count(*) AS cnt, sum(p.amount_kopecks) AS total_kopecks"
    )
    pay_result, _ = db.cypher_query(pay_query, {"uid": uid})
    pay_count = int(pay_result[0][0]) if pay_result else 0
    total_kopecks = int(pay_result[0][1]) if pay_result and pay_result[0][1] else 0

    from decimal import Decimal
    revenue_rubles = Decimal(str(total_kopecks)) / Decimal("100")
    ai_cost = usage["ai_cost"]
    profit = revenue_rubles - ai_cost

    detail = {
        "uid": uid,
        "plan_code": plan_code,
        "subscription_status": sub_status,
        "total_payments_count": pay_count,
        "total_payments_rubles": float(revenue_rubles),
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
        "cached_tokens": usage["cached_tokens"],
        "total_tokens": usage["total_tokens"],
        "ai_cost_rubles": float(ai_cost),
        "revenue_rubles": float(revenue_rubles),
        "profit_rubles": float(profit),
        "request_count": usage["request_count"],
        "last_ai_request": usage["last_request"],
    }

    logger.info("User detail: uid=%s, total_tokens=%d", uid, usage["total_tokens"])
    return detail


@router.get("/{uid}/usage")
async def get_user_usage(
    uid: str,
    limit: int = Query(default=100, ge=1, le=1000),
    admin: dict = Depends(get_current_admin),
):
    """История AI-использования пользователя (запросы с токенами)."""
    from neomodel import db

    query = (
        "MATCH (u:AIUsage {user_uid: $uid}) "
        "RETURN u.created_at AS created_at, "
        "       u.actual_input_tokens AS input_tokens, "
        "       u.actual_output_tokens AS output_tokens, "
        "       u.actual_cached_tokens AS cached_tokens, "
        "       u.actual_cost AS cost "
        "ORDER BY u.created_at DESC "
        "LIMIT $limit"
    )
    result, _ = db.cypher_query(query, {"uid": uid, "limit": limit})

    usage_records = []
    for row in result:
        usage_records.append({
            "created_at": str(row[0]) if row[0] else None,
            "input_tokens": int(row[1] or 0),
            "output_tokens": int(row[2] or 0),
            "cached_tokens": int(row[3] or 0),
            "total_tokens": int(row[1] or 0) + int(row[2] or 0) + int(row[3] or 0),
            "cost_rubles": float(row[4]) if row[4] else 0.0,
        })

    logger.info("User usage: uid=%s, records=%d", uid, len(usage_records))
    return {"uid": uid, "usage": usage_records}


@router.get("/{uid}/payments")
async def get_user_payments(
    uid: str,
    limit: int = Query(default=100, ge=1, le=1000),
    admin: dict = Depends(get_current_admin),
):
    """История платежей пользователя."""
    from neomodel import db

    query = (
        "MATCH (p:Payment {user_id: $uid}) "
        "RETURN p.uid AS uid, "
        "       p.amount_kopecks AS amount_kopecks, "
        "       p.status AS status, "
        "       p.plan_code AS plan_code, "
        "       p.created_at AS created_at "
        "ORDER BY p.created_at DESC "
        "LIMIT $limit"
    )
    result, _ = db.cypher_query(query, {"uid": uid, "limit": limit})

    payments = []
    for row in result:
        payments.append({
            "uid": str(row[0]) if row[0] else "",
            "amount_kopecks": int(row[1] or 0),
            "amount_rubles": float(int(row[1] or 0)) / 100.0,
            "status": str(row[2] or ""),
            "plan_code": str(row[3] or ""),
            "created_at": str(row[4]) if row[4] else None,
        })

    logger.info("User payments: uid=%s, count=%d", uid, len(payments))
    return {"uid": uid, "payments": payments}

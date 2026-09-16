"""
Layer: Frameworks & Drivers — Web
Package: web.routers.admin.sales
Responsibility: HTTP-контроллеры аналитики продаж в admin-панели.

Allowed imports: fastapi, web.dependencies, adapters.repositories.admin_repository
Forbidden imports: neomodel, services
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query

from adapters.repositories.admin_repository import AdminRepository
from web.dependencies import get_current_admin

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/overview")
async def sales_overview(
    admin: dict = Depends(get_current_admin),
):
    """Обзор продаж: количество, выручка, средний чек, возвраты."""
    repo = AdminRepository()
    stats = repo.get_total_sales_stats()

    logger.info("Sales overview: revenue=%s, refunds=%d",
                stats["total_revenue_rubles"], stats["refunds_count"])

    return {
        "total_sales_count": stats["total_sales_count"],
        "total_revenue_rubles": float(stats["total_revenue_rubles"]),
        "average_check_rubles": float(stats["average_check_rubles"]),
        "refunds_count": stats["refunds_count"],
        "refunds_amount_rubles": float(stats["refunds_amount_rubles"]),
        "net_revenue_rubles": float(stats["net_revenue_rubles"]),
    }


@router.get("/by-package")
async def sales_by_package(
    admin: dict = Depends(get_current_admin),
):
    """Продажи, сгруппированные по пакету/плану."""
    repo = AdminRepository()
    by_plan = repo.get_sales_by_plan()

    result = [
        {
            "plan_code": d["plan_code"],
            "sale_count": d["sale_count"],
            "total_kopecks": d["total_kopecks"],
            "revenue_rubles": float(d["revenue_rubles"]),
        }
        for d in by_plan
    ]

    logger.info("Sales by package: %d groups", len(result))
    return {"by_package": result}


@router.get("/by-plan")
async def sales_by_plan(
    admin: dict = Depends(get_current_admin),
):
    """Продажи, сгруппированные по plan_code."""
    repo = AdminRepository()
    by_plan = repo.get_sales_by_plan()

    result = [
        {
            "plan_code": d["plan_code"],
            "sale_count": d["sale_count"],
            "total_kopecks": d["total_kopecks"],
            "revenue_rubles": float(d["revenue_rubles"]),
        }
        for d in by_plan
    ]

    logger.info("Sales by plan: %d groups", len(result))
    return {"by_plan": result}


@router.get("/returns")
async def sales_returns(
    admin: dict = Depends(get_current_admin),
):
    """Список возвратов/рефандов."""
    from neomodel import db

    query = (
        "MATCH (r:Refund) "
        "WHERE r.status = 'SUCCEEDED' "
        "RETURN r.uid AS uid, "
        "       r.user_id AS user_id, "
        "       r.amount_kopecks AS amount_kopecks, "
        "       r.status AS status, "
        "       r.created_at AS created_at "
        "ORDER BY r.created_at DESC"
    )
    result, _ = db.cypher_query(query)

    returns = []
    for row in result:
        returns.append({
            "uid": str(row[0]) if row[0] else "",
            "user_id": str(row[1]) if row[1] else "",
            "amount_kopecks": int(row[2] or 0),
            "amount_rubles": float(int(row[2] or 0)) / 100.0,
            "status": str(row[3] or ""),
            "created_at": str(row[4]) if row[4] else None,
        })

    logger.info("Returns list: count=%d", len(returns))
    return {"returns": returns}

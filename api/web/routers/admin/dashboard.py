"""
Layer: Frameworks & Drivers — Web
Package: web.routers.admin.dashboard
Responsibility: HTTP-контроллеры dashboard-страницы admin-панели.

Allowed imports: fastapi, web.dependencies, adapters.repositories.admin_repository,
                 adapters.repositories.expense_repository, domain.rules.admin_calculations
Forbidden imports: neomodel, services
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from adapters.repositories.admin_repository import AdminRepository
from adapters.repositories.expense_repository import ExpenseRepository
from domain.models.admin import DashboardSummary, DashboardCharts, TimeSeriesPoint
from domain.rules.admin_calculations import (
    calculate_profitability,
    calculate_arpu,
    calculate_cac,
    calculate_ai_cost_per_user,
)
from web.dependencies import get_current_admin

logger = logging.getLogger(__name__)

router = APIRouter()


def _resolve_period(
    period: str,
    start_date: Optional[str],
    end_date: Optional[str],
) -> tuple[str, str]:
    """Возвращает (start_iso, end_iso) для выбранного периода."""
    if start_date and end_date:
        return start_date, end_date

    now = datetime.utcnow()
    if period == "day":
        start = now - timedelta(days=1)
    elif period == "week":
        start = now - timedelta(weeks=1)
    elif period == "month":
        start = now - timedelta(days=30)
    elif period == "quarter":
        start = now - timedelta(days=90)
    elif period == "year":
        start = now - timedelta(days=365)
    else:
        start = now - timedelta(days=30)

    return start.isoformat(), now.isoformat()


@router.get("/")
async def dashboard_summary(
    period: str = Query(default="month", regex="^(day|week|month|quarter|year)$"),
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
    admin: dict = Depends(get_current_admin),
):
    """Dashboard KPI: выручка, расходы, прибыль, маржа, ARPU, CAC."""
    start_iso, end_iso = _resolve_period(period, start_date, end_date)
    repo = AdminRepository()
    expense_repo = ExpenseRepository()

    total_users = repo.get_total_users()
    paying_users = repo.get_paying_users()
    period_days = max(1, (datetime.fromisoformat(end_iso) - datetime.fromisoformat(start_iso)).days)
    active_users = repo.get_active_users(period_days)

    revenue_data = repo.get_revenue_by_period("day", start_iso, end_iso)
    total_revenue_kopecks = sum(d["total_kopecks"] for d in revenue_data)
    revenue_rubles = Decimal(str(total_revenue_kopecks)) / Decimal("100")

    ai_cost_data = repo.get_ai_cost_by_period("day", start_iso, end_iso)
    total_ai_cost = sum(d["ai_cost_rubles"] for d in ai_cost_data)

    expense_summary = expense_repo.get_summary()
    infrastructure_cost = expense_summary.infrastructure_rubles
    tax = expense_summary.tax_rubles
    acquiring = expense_summary.acquiring_rubles
    advertising = expense_summary.advertising_rubles
    other_costs = expense_summary.other_rubles

    profitability = calculate_profitability(
        revenue=revenue_rubles,
        ai_cost=total_ai_cost,
        infrastructure_cost=infrastructure_cost,
        tax=tax,
        acquiring=acquiring,
        advertising=advertising,
        other_costs=other_costs,
    )

    arpu = calculate_arpu(revenue_rubles, paying_users)
    cac = calculate_cac(advertising, paying_users)
    ai_cost_per_user = calculate_ai_cost_per_user(total_ai_cost, paying_users)

    summary = DashboardSummary(
        revenue_rubles=profitability.revenue,
        expenses_rubles=profitability.total_costs,
        ai_cost_rubles=profitability.ai_cost,
        infrastructure_cost_rubles=profitability.infrastructure_cost,
        tax_rubles=profitability.tax,
        acquiring_rubles=profitability.acquiring,
        advertising_rubles=profitability.advertising,
        other_costs_rubles=profitability.other_costs,
        profit_rubles=profitability.profit,
        margin_pct=profitability.margin_pct,
        total_users=total_users,
        paying_users=paying_users,
        active_users=active_users,
        average_check_rubles=arpu,
        ai_cost_per_paying_user=ai_cost_per_user,
        cac_rubles=cac,
    )

    logger.info("Dashboard summary сформирован: revenue=%s, profit=%s", summary.revenue_rubles, summary.profit_rubles)

    return {
        "period": period,
        "start_date": start_iso,
        "end_date": end_iso,
        "revenue_rubles": float(summary.revenue_rubles),
        "expenses_rubles": float(summary.expenses_rubles),
        "ai_cost_rubles": float(summary.ai_cost_rubles),
        "infrastructure_cost_rubles": float(summary.infrastructure_cost_rubles),
        "tax_rubles": float(summary.tax_rubles),
        "acquiring_rubles": float(summary.acquiring_rubles),
        "advertising_rubles": float(summary.advertising_rubles),
        "other_costs_rubles": float(summary.other_costs_rubles),
        "profit_rubles": float(summary.profit_rubles),
        "margin_pct": float(summary.margin_pct),
        "total_users": summary.total_users,
        "paying_users": summary.paying_users,
        "active_users": summary.active_users,
        "average_check_rubles": float(summary.average_check_rubles),
        "ai_cost_per_paying_user": float(summary.ai_cost_per_paying_user),
        "cac_rubles": float(summary.cac_rubles),
    }


@router.get("/charts")
async def dashboard_charts(
    period: str = Query(default="month", regex="^(day|week|month|quarter|year)$"),
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
    admin: dict = Depends(get_current_admin),
):
    """Данные для графиков: выручка, расходы, AI-cost, прибыль по периодам."""
    start_iso, end_iso = _resolve_period(period, start_date, end_date)
    repo = AdminRepository()
    expense_repo = ExpenseRepository()

    revenue_by_period = repo.get_revenue_by_period(period, start_iso, end_iso)
    ai_cost_by_period = repo.get_ai_cost_by_period(period, start_iso, end_iso)

    ai_cost_map = {d["period"]: d["ai_cost_rubles"] for d in ai_cost_by_period}

    expense_summary = expense_repo.get_summary()
    total_expenses = expense_summary.total_rubles

    periods_sorted = sorted({d["period"] for d in revenue_by_period} | set(ai_cost_map.keys()))

    revenue_points: list[dict] = []
    expense_points: list[dict] = []
    ai_cost_points: list[dict] = []
    profit_points: list[dict] = []

    revenue_map = {d["period"]: Decimal(str(d["total_kopecks"])) / Decimal("100") for d in revenue_by_period}

    for p in periods_sorted:
        rev = revenue_map.get(p, Decimal("0"))
        ai = ai_cost_map.get(p, Decimal("0"))
        prof = rev - ai - total_expenses

        revenue_points.append({"date": p, "value": float(rev)})
        ai_cost_points.append({"date": p, "value": float(ai)})
        expense_points.append({"date": p, "value": float(total_expenses)})
        profit_points.append({"date": p, "value": float(prof)})

    logger.info("Dashboard charts сформированы: %d периодов", len(periods_sorted))

    return {
        "period": period,
        "start_date": start_iso,
        "end_date": end_iso,
        "revenue_by_period": revenue_points,
        "expenses_by_period": expense_points,
        "ai_cost_by_period": ai_cost_points,
        "profit_by_period": profit_points,
    }

"""
Layer: Frameworks & Drivers — Web
Package: web.routers.admin.unit_economics
Responsibility: HTTP-контроллеры unit economics в admin-панели.

Allowed imports: fastapi, web.dependencies, domain.rules.admin_calculations,
                 adapters.repositories.admin_repository
Forbidden imports: neomodel, services
"""
from __future__ import annotations

import logging
from decimal import Decimal

from fastapi import APIRouter, Depends, Query

from adapters.repositories.admin_repository import AdminRepository
from domain.rules.admin_calculations import (
    calculate_unit_economics,
    calculate_breakeven_users,
)
from web.dependencies import get_current_admin

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/")
async def unit_economics_all(
    admin: dict = Depends(get_current_admin),
):
    """Unit economics для всех пакетов токенов."""
    from neomodel import db

    plans_query = (
        "MATCH (s:Subscription) "
        "WHERE s.status = 'ACTIVE' "
        "RETURN DISTINCT s.plan_code AS plan_code"
    )
    plan_rows, _ = db.cypher_query(plans_query)
    plan_codes = [str(r[0]) for r in plan_rows if r[0]]

    if not plan_codes:
        return {"packages": []}

    repo = AdminRepository()
    all_aggregates = repo.get_all_users_usage_aggregates(period_days=365)

    price_query = (
        "MATCH (pv:ProviderPriceVersion {is_active: true}) "
        "RETURN pv.input_price_per_million AS input_price, "
        "       pv.output_price_per_million AS output_price, "
        "       pv.cache_input_price_per_million AS cache_price"
    )
    price_rows, _ = db.cypher_query(price_query)
    if price_rows:
        input_price_m = Decimal(str(price_rows[0][0] or "0"))
        output_price_m = Decimal(str(price_rows[0][1] or "0"))
        cache_price_m = Decimal(str(price_rows[0][2] or "0")) if price_rows[0][2] else Decimal("0")
    else:
        input_price_m = Decimal("0")
        output_price_m = Decimal("0")
        cache_price_m = Decimal("0")

    avg_input = sum(a["input_tokens"] for a in all_aggregates) / max(len(all_aggregates), 1)
    avg_output = sum(a["output_tokens"] for a in all_aggregates) / max(len(all_aggregates), 1)
    avg_cache = sum(a["cached_tokens"] for a in all_aggregates) / max(len(all_aggregates), 1)

    ai_cost_per_user = (
        Decimal(str(int(avg_input))) * input_price_m / Decimal("1000000")
        + Decimal(str(int(avg_output))) * output_price_m / Decimal("1000000")
        + Decimal(str(int(avg_cache))) * cache_price_m / Decimal("1000000")
    )

    package_prices: dict[str, dict] = {
        "basic": {"name": "Basic", "tokens": 5000000, "price": Decimal("990")},
        "standard": {"name": "Standard", "tokens": 20000000, "price": Decimal("2990")},
        "premium": {"name": "Premium", "tokens": 100000000, "price": Decimal("9990")},
    }

    result = []
    for plan_code in plan_codes:
        pkg = package_prices.get(plan_code.lower())
        if not pkg:
            pkg = {"name": plan_code, "tokens": 0, "price": Decimal("0")}

        ue = calculate_unit_economics(
            plan_code=plan_code,
            plan_name=pkg["name"],
            tokens_granted=pkg["tokens"],
            price_rubles=pkg["price"],
            ai_cost_rubles=ai_cost_per_user,
        )

        result.append({
            "plan_code": ue.plan_code,
            "plan_name": ue.plan_name,
            "tokens_granted": ue.tokens_granted,
            "price_rubles": float(ue.price_rubles),
            "ai_cost_rubles": float(ue.ai_cost_rubles),
            "tax_rubles": float(ue.tax_rubles),
            "acquiring_rubles": float(ue.acquiring_rubles),
            "cac_rubles": float(ue.cac_rubles),
            "contribution_profit_rubles": float(ue.contribution_profit_rubles),
            "contribution_margin_pct": float(ue.contribution_margin_pct),
        })

    logger.info("Unit economics: %d packages", len(result))
    return {"packages": result}


@router.get("/breakeven")
async def breakeven(
    avg_tokens_per_package: int = Query(default=10000000, gt=0, description="Среднее потребление токенов на пользователя"),
    admin: dict = Depends(get_current_admin),
):
    """Расчёт безубыточности (кол-во пользователей для break-even)."""
    from adapters.repositories.expense_repository import ExpenseRepository

    expense_repo = ExpenseRepository()
    summary = expense_repo.get_summary()
    fixed_costs = summary.fixed_rubles

    from neomodel import db
    price_query = (
        "MATCH (pv:ProviderPriceVersion {is_active: true}) "
        "RETURN pv.input_price_per_million AS input_price, "
        "       pv.output_price_per_million AS output_price, "
        "       pv.cache_input_price_per_million AS cache_price"
    )
    price_rows, _ = db.cypher_query(price_query)
    if price_rows:
        input_price_m = Decimal(str(price_rows[0][0] or "0"))
        output_price_m = Decimal(str(price_rows[0][1] or "0"))
        cache_price_m = Decimal(str(price_rows[0][2] or "0")) if price_rows[0][2] else Decimal("0")
    else:
        input_price_m = Decimal("0")
        output_price_m = Decimal("0")
        cache_price_m = Decimal("0")

    ai_cost_per_user = (
        Decimal(str(avg_tokens_per_package)) * Decimal("0.6") * input_price_m / Decimal("1000000")
        + Decimal(str(avg_tokens_per_package)) * Decimal("0.3") * output_price_m / Decimal("1000000")
        + Decimal(str(avg_tokens_per_package)) * Decimal("0.1") * cache_price_m / Decimal("1000000")
    )

    avg_check = Decimal("2000")
    acquiring_rate = Decimal("0.02")
    tax_rate = Decimal("0.06")

    acquiring = avg_check * acquiring_rate
    tax = avg_check * tax_rate
    contribution_profit = avg_check - ai_cost_per_user - acquiring - tax

    breakeven_users = calculate_breakeven_users(fixed_costs, contribution_profit)

    logger.info("Breakeven: fixed=%s, ai_cost=%s, users=%d", fixed_costs, ai_cost_per_user, breakeven_users)

    return {
        "fixed_costs_rubles": float(fixed_costs),
        "ai_cost_per_user_rubles": float(ai_cost_per_user),
        "avg_check_rubles": float(avg_check),
        "contribution_profit_rubles": float(contribution_profit),
        "breakeven_users": breakeven_users,
        "avg_tokens_per_package": avg_tokens_per_package,
    }

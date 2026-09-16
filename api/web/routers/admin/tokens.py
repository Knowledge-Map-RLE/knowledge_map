"""
Layer: Frameworks & Drivers — Web
Package: web.routers.admin.tokens
Responsibility: HTTP-контроллеры аналитики токенов в admin-панели.

Allowed imports: fastapi, web.dependencies, adapters.repositories.admin_repository
Forbidden imports: neomodel, services
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query

from adapters.repositories.admin_repository import AdminRepository
from web.dependencies import get_current_admin

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/overview")
async def token_overview(
    admin: dict = Depends(get_current_admin),
):
    """Обзор потребления токенов: агрегаты, доли, перцентили, стоимость."""
    repo = AdminRepository()
    percentiles = repo.get_token_percentiles()
    aggregates = repo.get_all_users_usage_aggregates(period_days=365)

    total_input = sum(a["input_tokens"] for a in aggregates)
    total_output = sum(a["output_tokens"] for a in aggregates)
    total_cached = sum(a["cached_tokens"] for a in aggregates)
    total_tokens = total_input + total_output + total_cached
    total_cost = sum(a["ai_cost"] for a in aggregates)

    user_count = len(aggregates) if aggregates else 1
    avg_per_user = total_tokens / user_count if aggregates else 0

    input_share = (total_input / total_tokens * 100) if total_tokens else 0
    output_share = (total_output / total_tokens * 100) if total_tokens else 0
    cache_share = (total_cached / total_tokens * 100) if total_tokens else 0

    logger.info("Token overview: total=%d, cost=%s", total_tokens, total_cost)

    return {
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "total_cached_tokens": total_cached,
        "total_tokens": total_tokens,
        "input_share_pct": round(input_share, 2),
        "output_share_pct": round(output_share, 2),
        "cache_share_pct": round(cache_share, 2),
        "avg_per_user": round(avg_per_user, 2),
        "p50": percentiles["p50"],
        "p90": percentiles["p90"],
        "p95": percentiles["p95"],
        "p99": percentiles["p99"],
        "total_ai_cost_rubles": float(total_cost),
    }


@router.get("/percentiles")
async def token_percentiles(
    admin: dict = Depends(get_current_admin),
):
    """Детальные перцентили потребления токенов."""
    repo = AdminRepository()
    percentiles = repo.get_token_percentiles()

    logger.info("Token percentiles: p50=%d, p90=%d, p95=%d, p99=%d",
                percentiles["p50"], percentiles["p90"], percentiles["p95"], percentiles["p99"])

    return percentiles


@router.get("/anomalies")
async def token_anomalies(
    z_threshold: float = Query(default=2.0, gt=0.0, le=10.0),
    admin: dict = Depends(get_current_admin),
):
    """Пользователи с аномально высоким потреблением токенов (z-score)."""
    repo = AdminRepository()
    anomalies = repo.get_anomaly_users(z_threshold=z_threshold)

    result = [
        {
            "uid": a["uid"],
            "total_tokens": a["total_tokens"],
            "ai_cost_rubles": float(a["ai_cost"]),
            "z_score": a["z_score"],
        }
        for a in anomalies
    ]

    logger.info("Token anomalies: count=%d, threshold=%.1f", len(result), z_threshold)
    return {"anomalies": result, "z_threshold": z_threshold}


@router.get("/cost")
async def token_cost_breakdown(
    admin: dict = Depends(get_current_admin),
):
    """Стоимость по типам токенов (input/output/cache)."""
    repo = AdminRepository()
    aggregates = repo.get_all_users_usage_aggregates(period_days=365)

    total_input_tokens = sum(a["input_tokens"] for a in aggregates)
    total_output_tokens = sum(a["output_tokens"] for a in aggregates)
    total_cached_tokens = sum(a["cached_tokens"] for a in aggregates)
    total_tokens = total_input_tokens + total_output_tokens + total_cached_tokens

    from infrastructure.neo4j.admin_models import ProviderPriceVersionNode
    from decimal import Decimal

    price_query = (
        "MATCH (pv:ProviderPriceVersion {is_active: true}) "
        "RETURN pv.input_price_per_million AS input_price, "
        "       pv.output_price_per_million AS output_price, "
        "       pv.cache_input_price_per_million AS cache_price"
    )
    from neomodel import db
    price_rows, _ = db.cypher_query(price_query)

    if price_rows:
        input_price = Decimal(str(price_rows[0][0] or "0")) / Decimal("1000000")
        output_price = Decimal(str(price_rows[0][1] or "0")) / Decimal("1000000")
        cache_price = Decimal(str(price_rows[0][2] or "0")) / Decimal("1000000") if price_rows[0][2] else Decimal("0")
    else:
        input_price = Decimal("0")
        output_price = Decimal("0")
        cache_price = Decimal("0")

    input_cost = Decimal(str(total_input_tokens)) * input_price
    output_cost = Decimal(str(total_output_tokens)) * output_price
    cache_cost = Decimal(str(total_cached_tokens)) * cache_price
    total_cost = input_cost + output_cost + cache_cost

    logger.info("Token cost breakdown: total=%s", total_cost)

    return {
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "total_cached_tokens": total_cached_tokens,
        "total_tokens": total_tokens,
        "input_price_per_token": float(input_price),
        "output_price_per_token": float(output_price),
        "cache_price_per_token": float(cache_price),
        "input_cost_rubles": float(input_cost),
        "output_cost_rubles": float(output_cost),
        "cache_cost_rubles": float(cache_cost),
        "total_cost_rubles": float(total_cost),
    }

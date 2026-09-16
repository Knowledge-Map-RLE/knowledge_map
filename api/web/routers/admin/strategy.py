"""
Layer: Frameworks & Drivers — Web
Package: web.routers.admin.strategy
Responsibility: HTTP-контроллеры стратегии развития в admin-панели.

Allowed imports: fastapi, web.dependencies, domain.rules.admin_calculations
Forbidden imports: neomodel, services
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from domain.rules.admin_calculations import calculate_capital_requirements, calculate_stage_economics
from web.dependencies import get_current_admin

logger = logging.getLogger(__name__)

router = APIRouter()


class StageCreateRequest(BaseModel):
    user_count: int = Field(..., ge=0, description="Количество пользователей на стадии")
    stage_name: str = Field(..., description="Название стадии")
    data: dict[str, Any] = Field(default_factory=dict, description="Параметры стадии для расчёта")


class CapitalRequest(BaseModel):
    monthly_fixed_costs: float = Field(..., gt=0, description="Ежемесячные фиксированные расходы (₽)")
    ai_cost_per_user: float = Field(..., ge=0, description="AI-стоимость на пользователя (₽)")
    users_before_revenue: int = Field(..., ge=0, description="Пользователи до дохода")
    months_to_breakeven: int = Field(..., ge=1, description="Месяцев до безубыточности")
    acquisition_cost_per_user: float = Field(default=0.0, ge=0, description="Стоимость привлечения (₽)")


@router.get("/stages")
async def list_stages(
    admin: dict = Depends(get_current_admin),
):
    """Список всех стадий развития."""
    from infrastructure.neo4j.admin_models import StrategyStageNode

    stages = StrategyStageNode.nodes.all()
    result = []
    for s in stages:
        data = {}
        try:
            data = json.loads(s.data_json)
        except (json.JSONDecodeError, TypeError):
            pass
        result.append({
            "uid": s.uid,
            "user_count": s.user_count,
            "stage_name": s.stage_name,
            "data": data,
            "created_by_uid": s.created_by_uid,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        })

    result.sort(key=lambda x: x["user_count"])
    logger.info("Stages list: count=%d", len(result))
    return {"stages": result}


@router.post("/stages", status_code=201)
async def create_or_update_stage(
    payload: StageCreateRequest,
    admin: dict = Depends(get_current_admin),
):
    """Создать/обновить стадию развития по user_count (upsert)."""
    from infrastructure.neo4j.admin_models import StrategyStageNode, AdminAuditLogNode
    from src.uuid8 import uuid8_str

    now = datetime.utcnow()

    existing = StrategyStageNode.nodes.get_or_none(user_count=payload.user_count)
    is_update = existing is not None

    if existing:
        existing.stage_name = payload.stage_name
        existing.data_json = json.dumps(payload.data, ensure_ascii=False)
        existing.updated_at = now
        existing.save()
        existing.refresh()
        node = existing
    else:
        node = StrategyStageNode(
            user_count=payload.user_count,
            stage_name=payload.stage_name,
            data_json=json.dumps(payload.data, ensure_ascii=False),
            created_by_uid=admin["uid"],
            created_at=now,
            updated_at=now,
        )
        node.save()
        node.refresh()

    _write_audit_log(
        admin_uid=admin["uid"],
        action="update" if is_update else "create",
        entity_type="strategy_stage",
        entity_uid=node.uid,
        new_value=json.dumps({"user_count": node.user_count, "stage_name": node.stage_name}),
    )

    logger.info("Stage %s: uid=%s, user_count=%d", "updated" if is_update else "created", node.uid, node.user_count)

    return {
        "success": True,
        "stage": {
            "uid": node.uid,
            "user_count": node.user_count,
            "stage_name": node.stage_name,
        },
    }


@router.get("/capital")
async def get_capital(
    admin: dict = Depends(get_current_admin),
):
    """Расчёт необходимого стартового капитала (значения по умолчанию)."""
    from adapters.repositories.expense_repository import ExpenseRepository

    expense_repo = ExpenseRepository()
    summary = expense_repo.get_summary()

    capital = calculate_capital_requirements(
        monthly_fixed_costs=summary.fixed_rubles,
        ai_cost_per_user=Decimal("50"),
        users_before_revenue=100,
        months_to_breakeven=6,
        acquisition_cost_per_user=Decimal("0"),
    )

    logger.info("Capital calculation: min=%s, base=%s", capital.min_capital_rubles, capital.base_capital_rubles)

    return {
        "min_capital_rubles": float(capital.min_capital_rubles),
        "base_capital_rubles": float(capital.base_capital_rubles),
        "conservative_capital_rubles": float(capital.conservative_capital_rubles),
        "monthly_fixed_costs_rubles": float(capital.monthly_fixed_costs_rubles),
        "months_to_breakeven": capital.months_to_breakeven,
        "max_negative_cashflow_rubles": float(capital.max_negative_cashflow_rubles),
    }


@router.post("/capital")
async def calculate_custom_capital(
    payload: CapitalRequest,
    admin: dict = Depends(get_current_admin),
):
    """Расчёт стартового капитала с пользовательскими параметрами."""
    capital = calculate_capital_requirements(
        monthly_fixed_costs=Decimal(str(payload.monthly_fixed_costs)),
        ai_cost_per_user=Decimal(str(payload.ai_cost_per_user)),
        users_before_revenue=payload.users_before_revenue,
        months_to_breakeven=payload.months_to_breakeven,
        acquisition_cost_per_user=Decimal(str(payload.acquisition_cost_per_user)),
    )

    logger.info("Custom capital calculation: min=%s", capital.min_capital_rubles)

    return {
        "min_capital_rubles": float(capital.min_capital_rubles),
        "base_capital_rubles": float(capital.base_capital_rubles),
        "conservative_capital_rubles": float(capital.conservative_capital_rubles),
        "monthly_fixed_costs_rubles": float(capital.monthly_fixed_costs_rubles),
        "months_to_breakeven": capital.months_to_breakeven,
        "max_negative_cashflow_rubles": float(capital.max_negative_cashflow_rubles),
    }


def _write_audit_log(
    *,
    admin_uid: str,
    action: str,
    entity_type: str,
    entity_uid: str,
    old_value: Optional[str] = None,
    new_value: Optional[str] = None,
) -> None:
    """Пишет запись в журнал аудита (fire-and-forget)."""
    try:
        from infrastructure.neo4j.admin_models import AdminAuditLogNode
        from src.uuid8 import uuid8_str

        node = AdminAuditLogNode(
            uid=uuid8_str(),
            admin_uid=admin_uid,
            action=action,
            entity_type=entity_type,
            entity_uid=entity_uid,
            old_value=old_value or "",
            new_value=new_value or "",
        )
        node.save()
    except Exception as exc:
        logger.warning("Не удалось записать audit log: %s", exc)

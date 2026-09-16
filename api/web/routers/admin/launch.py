"""
Layer: Frameworks & Drivers — Web
Package: web.routers.admin.launch
Responsibility: HTTP-контроллеры расчёта сценариев запуска в admin-панели.

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

from domain.rules.admin_calculations import calculate_launch_scenario
from web.dependencies import get_current_admin

logger = logging.getLogger(__name__)

router = APIRouter()


class LaunchParamsRequest(BaseModel):
    name: str = Field(..., description="Название сценария")
    params: dict[str, Any] = Field(
        ...,
        description="Параметры расчёта: audience_size, conversion_rates, avg_check_rubles, ai_cost_per_user_rubles, cac_rubles",
    )


class LaunchCalculateRequest(BaseModel):
    audience_size: int = Field(..., gt=0, description="Размер аудитории")
    conversion_rate: float = Field(..., gt=0, le=1, description="Конверсия в покупку")
    avg_check_rubles: float = Field(..., gt=0, description="Средний чек (₽)")
    ai_cost_per_user_rubles: float = Field(..., ge=0, description="AI-стоимость на пользователя (₽)")
    fixed_costs_rubles: float = Field(default=0.0, ge=0, description="Фиксированные расходы (₽)")
    cac_rubles: float = Field(default=0.0, ge=0, description="Стоимость привлечения (₽)")


@router.get("/scenarios")
async def list_scenarios(
    admin: dict = Depends(get_current_admin),
):
    """Список сохранённых сценариев запуска."""
    from infrastructure.neo4j.admin_models import LaunchScenarioNode

    scenarios = LaunchScenarioNode.nodes.all()
    result = []
    for s in scenarios:
        params = {}
        try:
            params = json.loads(s.params_json)
        except (json.JSONDecodeError, TypeError):
            pass
        result.append({
            "uid": s.uid,
            "name": s.name,
            "params": params,
            "created_by_uid": s.created_by_uid,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        })

    logger.info("Launch scenarios list: count=%d", len(result))
    return {"scenarios": result}


@router.post("/params", status_code=201)
async def save_launch_params(
    payload: LaunchParamsRequest,
    admin: dict = Depends(get_current_admin),
):
    """Сохранить параметры сценария запуска."""
    from infrastructure.neo4j.admin_models import LaunchScenarioNode, AdminAuditLogNode
    from src.uuid8 import uuid8_str

    now = datetime.utcnow()
    node = LaunchScenarioNode(
        name=payload.name,
        params_json=json.dumps(payload.params, ensure_ascii=False),
        created_by_uid=admin["uid"],
        created_at=now,
        updated_at=now,
    )
    node.save()
    node.refresh()

    _write_audit_log(
        admin_uid=admin["uid"],
        action="create",
        entity_type="launch_scenario",
        entity_uid=node.uid,
        new_value=json.dumps({"name": node.name}),
    )

    logger.info("Launch params saved: uid=%s, name=%s", node.uid, node.name)

    return {
        "success": True,
        "scenario": {
            "uid": node.uid,
            "name": node.name,
        },
    }


@router.post("/calculate")
async def calculate_launch(
    payload: LaunchCalculateRequest,
    admin: dict = Depends(get_current_admin),
):
    """Рассчитать сценарий запуска по параметрам."""
    result = calculate_launch_scenario(
        audience_size=payload.audience_size,
        conversion_rate=Decimal(str(payload.conversion_rate)),
        avg_check_rubles=Decimal(str(payload.avg_check_rubles)),
        ai_cost_per_user_rubles=Decimal(str(payload.ai_cost_per_user_rubles)),
        fixed_costs_rubles=Decimal(str(payload.fixed_costs_rubles)),
        cac_rubles=Decimal(str(payload.cac_rubles)),
    )

    logger.info("Launch calculated: buyers=%d, profit=%s", result.buyers, result.profit_rubles)

    return {
        "audience_size": result.audience_size,
        "conversion_rate": float(result.conversion_rate),
        "visitors": result.visitors,
        "registrations": result.registrations,
        "buyers": result.buyers,
        "revenue_rubles": float(result.revenue_rubles),
        "ai_cost_rubles": float(result.ai_cost_rubles),
        "expenses_rubles": float(result.expenses_rubles),
        "profit_rubles": float(result.profit_rubles),
        "required_capital_rubles": float(result.required_capital_rubles),
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

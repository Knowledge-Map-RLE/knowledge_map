"""
Layer: Frameworks & Drivers — Web
Package: web.routers.admin.plan
Responsibility: HTTP-контроллеры финансового плана в admin-панели.

Allowed imports: fastapi, web.dependencies, adapters.repositories.admin_repository,
                 domain.rules.plan_vs_fact
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

from web.dependencies import get_current_admin

logger = logging.getLogger(__name__)

router = APIRouter()


class FinancialPlanCreateRequest(BaseModel):
    name: str = Field(..., description="Название версии плана")
    data: dict[str, Any] = Field(..., description="JSON с плановыми значениями метрик")


@router.get("/")
async def get_active_plan(
    admin: dict = Depends(get_current_admin),
):
    """Получить текущий активный финансовый план."""
    from infrastructure.neo4j.admin_models import FinancialPlanNode

    plan = FinancialPlanNode.nodes.get_or_none(is_active=True)
    if not plan:
        raise HTTPException(status_code=404, detail="Активный финансовый план не найден")

    data = {}
    try:
        data = json.loads(plan.data_json)
    except (json.JSONDecodeError, TypeError):
        pass

    logger.info("Active plan fetched: uid=%s, version=%d", plan.uid, plan.version)

    return {
        "uid": plan.uid,
        "version": plan.version,
        "name": plan.name,
        "data": data,
        "is_active": plan.is_active,
        "created_by_uid": plan.created_by_uid,
        "created_at": plan.created_at.isoformat() if plan.created_at else None,
        "updated_at": plan.updated_at.isoformat() if plan.updated_at else None,
    }


@router.post("/", status_code=201)
async def create_or_update_plan(
    payload: FinancialPlanCreateRequest,
    admin: dict = Depends(get_current_admin),
):
    """Создать/обновить финансовый план. Деактивирует предыдущий."""
    from infrastructure.neo4j.admin_models import FinancialPlanNode, AdminAuditLogNode
    from src.uuid8 import uuid8_str

    now = datetime.utcnow()

    prev_active = FinancialPlanNode.nodes.get_or_none(is_active=True)
    old_uid = prev_active.uid if prev_active else None

    if prev_active:
        prev_active.is_active = False
        prev_active.updated_at = now
        prev_active.save()

    max_version_query = (
        "MATCH (p:FinancialPlan) "
        "RETURN max(p.version) AS max_ver"
    )
    from neomodel import db
    result, _ = db.cypher_query(max_version_query)
    max_version = int(result[0][0] or 0) if result else 0

    node = FinancialPlanNode(
        version=max_version + 1,
        name=payload.name,
        data_json=json.dumps(payload.data, ensure_ascii=False),
        is_active=True,
        created_by_uid=admin["uid"],
        created_at=now,
        updated_at=now,
    )
    node.save()
    node.refresh()

    _write_audit_log(
        admin_uid=admin["uid"],
        action="create_plan",
        entity_type="financial_plan",
        entity_uid=node.uid,
        old_value=json.dumps({"old_plan_uid": old_uid}) if old_uid else None,
        new_value=json.dumps({"name": node.name, "version": node.version}),
    )

    logger.info("Financial plan created: uid=%s, version=%d", node.uid, node.version)

    return {
        "success": True,
        "plan": {
            "uid": node.uid,
            "version": node.version,
            "name": node.name,
        },
    }


@router.get("/plan-vs-fact")
async def plan_vs_fact(
    admin: dict = Depends(get_current_admin),
):
    """Сравнение плановых и фактических показателей."""
    from infrastructure.neo4j.admin_models import FinancialPlanNode
    from adapters.repositories.admin_repository import AdminRepository
    from adapters.repositories.expense_repository import ExpenseRepository
    from domain.rules.plan_vs_fact import compare_plan_vs_fact, summarize_plan_vs_fact

    plan_node = FinancialPlanNode.nodes.get_or_none(is_active=True)
    if not plan_node:
        raise HTTPException(status_code=404, detail="Активный финансовый план не найден")

    try:
        plan_data = json.loads(plan_node.data_json)
    except (json.JSONDecodeError, TypeError):
        raise HTTPException(status_code=500, detail="Невалидный JSON в финансовом плане")

    repo = AdminRepository()
    expense_repo = ExpenseRepository()

    total_users = repo.get_total_users()
    paying_users = repo.get_paying_users()

    revenue_data = repo.get_revenue_by_period("month", "2020-01-01", datetime.utcnow().isoformat())
    total_revenue_kopecks = sum(d["total_kopecks"] for d in revenue_data)
    revenue_rubles = Decimal(str(total_revenue_kopecks)) / Decimal("100")

    ai_cost_data = repo.get_ai_cost_by_period("month", "2020-01-01", datetime.utcnow().isoformat())
    total_ai_cost = sum(d["ai_cost_rubles"] for d in ai_cost_data)

    expense_summary = expense_repo.get_summary()
    tax = expense_summary.tax_rubles
    acquiring = expense_summary.acquiring_rubles
    advertising = expense_summary.advertising_rubles
    infrastructure = expense_summary.infrastructure_rubles

    profit = revenue_rubles - total_ai_cost - tax - acquiring - advertising - infrastructure
    margin = (profit / revenue_rubles * 100) if revenue_rubles > 0 else Decimal("0")

    fact = {
        "users": Decimal(str(total_users)),
        "paying_users": Decimal(str(paying_users)),
        "conversion_rate": (Decimal(str(paying_users)) / Decimal(str(total_users)) * 100) if total_users > 0 else Decimal("0"),
        "avg_check": (revenue_rubles / Decimal(str(paying_users))) if paying_users > 0 else Decimal("0"),
        "ai_cost": total_ai_cost,
        "revenue": revenue_rubles,
        "profit": profit.quantize(Decimal("0.01")),
        "margin": margin.quantize(Decimal("0.01")),
        "infrastructure_cost": infrastructure,
        "tax": tax,
        "acquiring": acquiring,
        "cac": advertising,
    }

    plan_decoded: dict[str, Decimal] = {}
    for k, v in plan_data.items():
        if isinstance(v, (int, float)):
            plan_decoded[k] = Decimal(str(v))

    items = compare_plan_vs_fact(plan_decoded, fact)
    summary = summarize_plan_vs_fact(items)

    logger.info("Plan vs fact: total_metrics=%d, anomalies=%d", summary["total_metrics"], summary["anomalies_count"])

    return {
        "plan_name": plan_node.name,
        "plan_version": plan_node.version,
        "items": [
            {
                "metric_name": i.metric_name,
                "metric_label": i.metric_label,
                "plan_value": float(i.plan_value),
                "fact_value": float(i.fact_value),
                "deviation_abs": float(i.deviation_abs),
                "deviation_pct": float(i.deviation_pct),
                "formula": i.formula,
                "unit": i.unit,
            }
            for i in items
        ],
        "summary": {
            "total_metrics": summary["total_metrics"],
            "better_than_plan": summary["better_than_plan"],
            "worse_than_plan": summary["worse_than_plan"],
            "on_plan": summary["on_plan"],
            "anomalies_count": summary["anomalies_count"],
        },
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

"""
Layer: Frameworks & Drivers — Web
Package: web.routers.admin.expenses
Responsibility: HTTP-контроллеры CRUD расходов в admin-панели.

Allowed imports: fastapi, web.dependencies, adapters.repositories.expense_repository,
                 infrastructure.neo4j.admin_models
Forbidden imports: neomodel (напрямую), services
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from adapters.repositories.expense_repository import ExpenseRepository
from web.dependencies import get_current_admin

logger = logging.getLogger(__name__)

router = APIRouter()


class ExpenseCreateRequest(BaseModel):
    category: str = Field(..., description="infrastructure | ai_tokens | acquiring | advertising | tax | other")
    subcategory: str = Field(default="", description="Подкатегория")
    description: str = Field(..., description="Описание расхода")
    amount_kopecks: int = Field(..., ge=0, description="Сумма в копейках")
    currency: str = Field(default="RUB")
    period_start: str = Field(..., description="ISO-дата начала периода")
    period_end: str = Field(..., description="ISO-дата окончания периода")
    is_recurring: bool = Field(default=False)
    is_fixed: bool = Field(default=False)
    source: str = Field(default="manual", description="manual | auto")


class ExpenseUpdateRequest(BaseModel):
    category: Optional[str] = None
    subcategory: Optional[str] = None
    description: Optional[str] = None
    amount_kopecks: Optional[int] = Field(default=None, ge=0)
    currency: Optional[str] = None
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    is_recurring: Optional[bool] = None
    is_fixed: Optional[bool] = None
    source: Optional[str] = None


@router.get("/")
async def list_expenses(
    category: Optional[str] = Query(default=None),
    is_fixed: Optional[bool] = Query(default=None),
    period_start: Optional[str] = Query(default=None),
    period_end: Optional[str] = Query(default=None),
    admin: dict = Depends(get_current_admin),
):
    """Список расходов с фильтрами."""
    repo = ExpenseRepository()
    filters: dict = {}
    if category:
        filters["category"] = category
    if is_fixed is not None:
        filters["is_fixed"] = is_fixed
    if period_start:
        filters["period_start"] = period_start
    if period_end:
        filters["period_end"] = period_end

    expenses = repo.get_all(filters=filters if filters else None)

    result = [
        {
            "uid": e.uid,
            "category": e.category,
            "subcategory": e.subcategory,
            "description": e.description,
            "amount_kopecks": e.amount_kopecks,
            "amount_rubles": float(e.amount_rubles),
            "currency": e.currency,
            "period_start": e.period_start,
            "period_end": e.period_end,
            "is_recurring": e.is_recurring,
            "is_fixed": e.is_fixed,
            "source": e.source,
            "created_by_uid": e.created_by_uid,
            "created_at": e.created_at,
            "updated_at": e.updated_at,
        }
        for e in expenses
    ]

    logger.info("Expenses list: count=%d", len(result))
    return {"expenses": result}


@router.post("/", status_code=201)
async def create_expense(
    payload: ExpenseCreateRequest,
    admin: dict = Depends(get_current_admin),
):
    """Создать расход. Создаёт запись в журнале аудита."""
    repo = ExpenseRepository()

    expense = repo.create({
        "category": payload.category,
        "subcategory": payload.subcategory,
        "description": payload.description,
        "amount_kopecks": payload.amount_kopecks,
        "currency": payload.currency,
        "period_start": payload.period_start,
        "period_end": payload.period_end,
        "is_recurring": payload.is_recurring,
        "is_fixed": payload.is_fixed,
        "source": payload.source,
        "created_by_uid": admin["uid"],
    })

    _write_audit_log(
        admin_uid=admin["uid"],
        action="create",
        entity_type="expense",
        entity_uid=expense.uid,
        new_value=json.dumps({"category": expense.category, "amount_kopecks": expense.amount_kopecks}),
    )

    logger.info("Expense created: uid=%s, category=%s, amount=%d", expense.uid, expense.category, expense.amount_kopecks)

    return {
        "success": True,
        "expense": {
            "uid": expense.uid,
            "category": expense.category,
            "amount_kopecks": expense.amount_kopecks,
            "amount_rubles": float(expense.amount_rubles),
        },
    }


@router.put("/{uid}")
async def update_expense(
    uid: str,
    payload: ExpenseUpdateRequest,
    admin: dict = Depends(get_current_admin),
):
    """Обновить расход. Создаёт запись в журнале аудита."""
    repo = ExpenseRepository()
    existing = repo.get_by_uid(uid)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Расход {uid} не найден")

    update_data = payload.model_dump(exclude_unset=True)
    expense = repo.update(uid, update_data)
    if not expense:
        raise HTTPException(status_code=500, detail="Ошибка обновления расхода")

    _write_audit_log(
        admin_uid=admin["uid"],
        action="update",
        entity_type="expense",
        entity_uid=uid,
        old_value=json.dumps({"amount_kopecks": existing.amount_kopecks, "category": existing.category}),
        new_value=json.dumps({"amount_kopecks": expense.amount_kopecks, "category": expense.category}),
    )

    logger.info("Expense updated: uid=%s", uid)

    return {
        "success": True,
        "expense": {
            "uid": expense.uid,
            "category": expense.category,
            "amount_kopecks": expense.amount_kopecks,
            "amount_rubles": float(expense.amount_rubles),
        },
    }


@router.delete("/{uid}")
async def delete_expense(
    uid: str,
    admin: dict = Depends(get_current_admin),
):
    """Удалить расход. Создаёт запись в журнале аудита."""
    repo = ExpenseRepository()
    existing = repo.get_by_uid(uid)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Расход {uid} не найден")

    deleted = repo.delete(uid)
    if not deleted:
        raise HTTPException(status_code=500, detail="Ошибка удаления расхода")

    _write_audit_log(
        admin_uid=admin["uid"],
        action="delete",
        entity_type="expense",
        entity_uid=uid,
        old_value=json.dumps({"category": existing.category, "amount_kopecks": existing.amount_kopecks}),
    )

    logger.info("Expense deleted: uid=%s", uid)
    return {"success": True}


@router.get("/summary")
async def expense_summary(
    admin: dict = Depends(get_current_admin),
):
    """Агрегация расходов по категориям."""
    repo = ExpenseRepository()
    summary = repo.get_summary()

    logger.info("Expense summary: total=%s", summary.total_rubles)

    return {
        "total_rubles": float(summary.total_rubles),
        "infrastructure_rubles": float(summary.infrastructure_rubles),
        "ai_tokens_rubles": float(summary.ai_tokens_rubles),
        "acquiring_rubles": float(summary.acquiring_rubles),
        "advertising_rubles": float(summary.advertising_rubles),
        "tax_rubles": float(summary.tax_rubles),
        "other_rubles": float(summary.other_rubles),
        "fixed_rubles": float(summary.fixed_rubles),
        "variable_rubles": float(summary.variable_rubles),
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

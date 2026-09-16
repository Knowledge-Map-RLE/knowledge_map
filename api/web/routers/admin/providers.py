"""
Layer: Frameworks & Drivers — Web
Package: web.routers.admin.providers
Responsibility: HTTP-контроллеры управления AI-провайдерами в admin-панели.

Allowed imports: fastapi, web.dependencies, infrastructure.neo4j.admin_models,
                 infrastructure.neo4j.orm_models
Forbidden imports: neomodel (напрямую в router — только через models), services
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from web.dependencies import get_current_admin

logger = logging.getLogger(__name__)

router = APIRouter()


class ProviderCreateRequest(BaseModel):
    name: str = Field(..., description="Уникальное имя провайдера (cloudru, deepseek, ...)")
    display_name: str = Field(..., description="Отображаемое имя")
    base_url: Optional[str] = Field(default=None, description="Базовый URL API")


class ProviderUpdateRequest(BaseModel):
    display_name: Optional[str] = None
    base_url: Optional[str] = None
    is_active: Optional[bool] = None


class PriceVersionCreateRequest(BaseModel):
    model: str = Field(..., description="Имя модели (deepseek-chat, cloudru-v1, ...)")
    input_price_per_million: float = Field(..., gt=0, description="Цена input за 1M токенов (₽)")
    output_price_per_million: float = Field(..., gt=0, description="Цена output за 1M токенов (₽)")
    cache_input_price_per_million: Optional[float] = Field(default=None, ge=0)
    currency: str = Field(default="RUB")
    is_active: bool = Field(default=True)


@router.get("/")
async def list_providers(
    admin: dict = Depends(get_current_admin),
):
    """Список всех AI-провайдеров."""
    from infrastructure.neo4j.admin_models import AIProviderNode

    providers = AIProviderNode.nodes.all()
    result = [
        {
            "uid": p.uid,
            "name": p.name,
            "display_name": p.display_name,
            "base_url": p.base_url,
            "is_active": p.is_active,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        }
        for p in providers
    ]

    logger.info("Providers list: count=%d", len(result))
    return {"providers": result}


@router.post("/", status_code=201)
async def create_provider(
    payload: ProviderCreateRequest,
    admin: dict = Depends(get_current_admin),
):
    """Создать AI-провайдер. Запись в журнале аудита."""
    from infrastructure.neo4j.admin_models import AIProviderNode, AdminAuditLogNode
    from src.uuid8 import uuid8_str

    existing = AIProviderNode.nodes.get_or_none(name=payload.name)
    if existing:
        raise HTTPException(status_code=409, detail=f"Провайдер с именем '{payload.name}' уже существует")

    now = datetime.utcnow()
    node = AIProviderNode(
        name=payload.name,
        display_name=payload.display_name,
        base_url=payload.base_url or "",
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    node.save()
    node.refresh()

    _write_audit_log(
        admin_uid=admin["uid"],
        action="create",
        entity_type="provider",
        entity_uid=node.uid,
        new_value=json.dumps({"name": node.name, "display_name": node.display_name}),
    )

    logger.info("Provider created: uid=%s, name=%s", node.uid, node.name)

    return {
        "success": True,
        "provider": {
            "uid": node.uid,
            "name": node.name,
            "display_name": node.display_name,
        },
    }


@router.put("/{uid}")
async def update_provider(
    uid: str,
    payload: ProviderUpdateRequest,
    admin: dict = Depends(get_current_admin),
):
    """Обновить AI-провайдер. Запись в журнале аудита."""
    from infrastructure.neo4j.admin_models import AIProviderNode

    try:
        node = AIProviderNode.nodes.get(uid=uid)
    except Exception:
        raise HTTPException(status_code=404, detail=f"Провайдер {uid} не найден")

    old_name = node.name
    if payload.display_name is not None:
        node.display_name = payload.display_name
    if payload.base_url is not None:
        node.base_url = payload.base_url
    if payload.is_active is not None:
        node.is_active = payload.is_active

    node.updated_at = datetime.utcnow()
    node.save()
    node.refresh()

    _write_audit_log(
        admin_uid=admin["uid"],
        action="update",
        entity_type="provider",
        entity_uid=uid,
        old_value=json.dumps({"name": old_name}),
        new_value=json.dumps({"name": node.name, "is_active": node.is_active}),
    )

    logger.info("Provider updated: uid=%s", uid)

    return {
        "success": True,
        "provider": {
            "uid": node.uid,
            "name": node.name,
            "display_name": node.display_name,
            "is_active": node.is_active,
        },
    }


@router.get("/{uid}/prices")
async def get_provider_prices(
    uid: str,
    admin: dict = Depends(get_current_admin),
):
    """История версий тарифов провайдера."""
    from infrastructure.neo4j.admin_models import AIProviderNode, ProviderPriceVersionNode

    try:
        AIProviderNode.nodes.get(uid=uid)
    except Exception:
        raise HTTPException(status_code=404, detail=f"Провайдер {uid} не найден")

    prices = ProviderPriceVersionNode.nodes.filter(provider_uid=uid).order_by("-created_at")

    result = [
        {
            "uid": p.uid,
            "provider_uid": p.provider_uid,
            "model": p.model,
            "input_price_per_million": float(p.input_price_per_million),
            "output_price_per_million": float(p.output_price_per_million),
            "cache_input_price_per_million": float(p.cache_input_price_per_million) if p.cache_input_price_per_million else None,
            "currency": p.currency,
            "valid_from": p.valid_from.isoformat() if p.valid_from else None,
            "valid_to": p.valid_to.isoformat() if p.valid_to else None,
            "is_active": p.is_active,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in prices
    ]

    logger.info("Provider prices: provider_uid=%s, count=%d", uid, len(result))
    return {"provider_uid": uid, "prices": result}


@router.post("/{uid}/prices", status_code=201)
async def create_price_version(
    uid: str,
    payload: PriceVersionCreateRequest,
    admin: dict = Depends(get_current_admin),
):
    """Создать новую версию тарифа. Деактивирует предыдущую для той же модели."""
    from infrastructure.neo4j.admin_models import (
        AIProviderNode,
        ProviderPriceVersionNode,
        AdminAuditLogNode,
    )
    from src.uuid8 import uuid8_str

    try:
        AIProviderNode.nodes.get(uid=uid)
    except Exception:
        raise HTTPException(status_code=404, detail=f"Провайдер {uid} не найден")

    now = datetime.utcnow()

    prev_active = ProviderPriceVersionNode.nodes.filter(
        provider_uid=uid, model=payload.model, is_active=True
    )
    for p in prev_active:
        p.is_active = False
        p.valid_to = now
        p.save()

    node = ProviderPriceVersionNode(
        provider_uid=uid,
        model=payload.model,
        input_price_per_million=str(payload.input_price_per_million),
        output_price_per_million=str(payload.output_price_per_million),
        cache_input_price_per_million=str(payload.cache_input_price_per_million) if payload.cache_input_price_per_million is not None else "",
        currency=payload.currency,
        valid_from=now,
        is_active=payload.is_active,
        created_at=now,
    )
    node.save()
    node.refresh()

    _write_audit_log(
        admin_uid=admin["uid"],
        action="create_price_version",
        entity_type="provider_price",
        entity_uid=node.uid,
        new_value=json.dumps({
            "provider_uid": uid,
            "model": payload.model,
            "input_price": payload.input_price_per_million,
            "output_price": payload.output_price_per_million,
        }),
    )

    logger.info("Price version created: uid=%s, provider=%s, model=%s", node.uid, uid, payload.model)

    return {
        "success": True,
        "price_version": {
            "uid": node.uid,
            "provider_uid": uid,
            "model": payload.model,
            "input_price_per_million": payload.input_price_per_million,
            "output_price_per_million": payload.output_price_per_million,
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

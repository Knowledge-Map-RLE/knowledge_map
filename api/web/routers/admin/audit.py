"""
Layer: Frameworks & Drivers — Web
Package: web.routers.admin.audit
Responsibility: HTTP-контроллер журнала действий администратора.

Allowed imports: fastapi, web.dependencies, infrastructure.neo4j.admin_models
Forbidden imports: neomodel (напрямую), services
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query

from web.dependencies import get_current_admin

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/")
async def list_audit_log(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    admin_uid: Optional[str] = Query(default=None, description="Фильтр по UID администратора"),
    action: Optional[str] = Query(default=None, description="Фильтр по типу действия"),
    entity_type: Optional[str] = Query(default=None, description="Фильтр по типу сущности"),
    start_date: Optional[str] = Query(default=None, description="ISO-дата начала"),
    end_date: Optional[str] = Query(default=None, description="ISO-дата окончания"),
    admin: dict = Depends(get_current_admin),
):
    """Журнал действий администратора с пагинацией и фильтрами."""
    from infrastructure.neo4j.admin_models import AdminAuditLogNode

    nodeset = AdminAuditLogNode.nodes

    if admin_uid:
        nodeset = nodeset.filter(admin_uid=admin_uid)
    if action:
        nodeset = nodeset.filter(action=action)
    if entity_type:
        nodeset = nodeset.filter(entity_type=entity_type)

    all_entries = list(nodeset.order_by("-created_at"))

    if start_date:
        all_entries = [e for e in all_entries if e.created_at and e.created_at.isoformat() >= start_date]
    if end_date:
        all_entries = [e for e in all_entries if e.created_at and e.created_at.isoformat() <= end_date]

    total = len(all_entries)
    offset = (page - 1) * page_size
    page_entries = all_entries[offset : offset + page_size]

    result = [
        {
            "uid": e.uid,
            "admin_uid": e.admin_uid,
            "action": e.action,
            "entity_type": e.entity_type,
            "entity_uid": e.entity_uid,
            "old_value": e.old_value or None,
            "new_value": e.new_value or None,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in page_entries
    ]

    logger.info("Audit log: total=%d, page=%d, page_size=%d", total, page, page_size)

    return {
        "entries": result,
        "total": total,
        "page": page,
        "page_size": page_size,
    }

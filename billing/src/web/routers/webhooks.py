"""
Layer: Frameworks & Drivers — Web
Package: web.routers.webhooks
Responsibility: Приём уведомлений ЮKassa.

Провайдер не подписывает уведомления — безопасность обеспечена
идемпотентностью (external_event_id) и перепроверкой статуса/суммы
через API провайдера (см. ProcessProviderEvent).
"""
import logging
from typing import Dict

from fastapi import APIRouter, Depends, Request

from application.webhooks.process_provider_event import ProcessProviderEvent
from web.dependencies import get_process_provider_event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing/webhooks", tags=["webhooks"])


@router.post("/yookassa")
async def yookassa_webhook(
    request: Request,
    process_provider_event: ProcessProviderEvent = Depends(get_process_provider_event),
) -> Dict[str, str]:
    payload = await _read_payload(request)
    result = await process_provider_event.execute(payload)
    logger.info(
        "Webhook event=%s -> %s (%s)",
        payload.get("event"),
        result.status,
        result.detail,
    )
    return {"status": result.status}


async def _read_payload(request: Request) -> Dict:
    try:
        return await request.json()
    except Exception:
        form = await request.form()
        return {key: value for key, value in form.items()}

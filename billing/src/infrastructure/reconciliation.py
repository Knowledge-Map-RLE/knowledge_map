"""
Layer: Frameworks & Drivers — Infrastructure
Package: infrastructure.reconciliation
Responsibility: Фоновая сверка незавершённых платежей с провайдером.

Страховка от пропущенных вебхуков: подтягивает статусы PENDING/CREATED
платежей старше RECONCILIATION_GRACE_SECONDS и пропускает их через тот же
идемпотентный обработчик ProcessProviderEvent.
"""
import asyncio
import logging
from datetime import timedelta

from application.ports.payment_gateway import PaymentProviderProtocol
from application.ports.repositories import PaymentRepositoryProtocol
from application.webhooks.process_provider_event import ProcessProviderEvent
from domain.rules.time import utcnow

logger = logging.getLogger(__name__)

RECONCILIATION_GRACE_SECONDS = 600


async def reconciliation_loop(
    *,
    payment_repository: PaymentRepositoryProtocol,
    payment_gateway: PaymentProviderProtocol,
    process_provider_event: ProcessProviderEvent,
    interval_seconds: int,
    grace_seconds: int = RECONCILIATION_GRACE_SECONDS,
) -> None:
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            await _reconcile_once(
                payment_repository=payment_repository,
                payment_gateway=payment_gateway,
                process_provider_event=process_provider_event,
                grace_seconds=grace_seconds,
            )
        except Exception:
            logger.exception("Reconciliation pass failed")


async def _reconcile_once(
    *,
    payment_repository: PaymentRepositoryProtocol,
    payment_gateway: PaymentProviderProtocol,
    process_provider_event: ProcessProviderEvent,
    grace_seconds: int,
) -> None:
    since = utcnow() - timedelta(seconds=grace_seconds)
    pending = payment_repository.list_pending_since(since)
    if not pending:
        return
    logger.info("Reconciliation: %d pending payments older than %ss", len(pending), grace_seconds)
    for payment in pending:
        if not payment.provider_payment_id:
            continue
        try:
            gateway_payment = await payment_gateway.get_payment(payment.provider_payment_id)
        except Exception as exc:
            logger.warning("Reconciliation: cannot fetch %s: %s", payment.provider_payment_id, exc)
            continue
        event_type = _status_to_event(gateway_payment.status)
        if event_type is None:
            continue
        result = await process_provider_event.execute(
            {
                "event": event_type,
                "object": {"id": payment.provider_payment_id},
            }
        )
        logger.info(
            "Reconciliation %s -> %s (%s)",
            payment.provider_payment_id,
            event_type,
            result.status,
        )


def _status_to_event(status: str) -> str | None:
    if status == "succeeded":
        return "payment.succeeded"
    if status == "canceled":
        return "payment.canceled"
    return None

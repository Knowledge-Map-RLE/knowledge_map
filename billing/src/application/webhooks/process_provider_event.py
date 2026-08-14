"""
Layer: Application
Package: application.webhooks.process_provider_event
Responsibility: Идемпотентная обработка событий провайдера (ЮKassa).
"""
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional

from neomodel import db
from neomodel.exceptions import UniqueProperty

from application.ports.payment_gateway import GatewayPayment, PaymentProviderProtocol
from application.ports.repositories import (
    CreditRepositoryProtocol,
    PaymentEventRepositoryProtocol,
    PaymentRepositoryProtocol,
    PlanRepositoryProtocol,
    RefundRepositoryProtocol,
    SubscriptionRepositoryProtocol,
)
from application.subscriptions.activate_subscription import ActivateSubscription
from domain.exceptions import ProviderError, WebhookError
from domain.models import Payment, PaymentEvent, Refund
from domain.models.payment import PaymentStatus
from domain.models.refund import RefundStatus
from domain.rules.money import value_to_kopecks
from domain.rules.payment_state import can_transition, transition
from domain.rules.time import utcnow

logger = logging.getLogger(__name__)

SUPPORTED_EVENTS = {
    "payment.succeeded",
    "payment.canceled",
    "refund.succeeded",
}


class ProcessingStatus:
    PROCESSED = "processed"
    ALREADY_PROCESSED = "already_processed"
    IGNORED = "ignored"
    REJECTED = "rejected"


@dataclass(frozen=True)
class ProcessingResult:
    status: str
    detail: str = ""


class ProcessProviderEvent:
    def __init__(
        self,
        payment_event_repository: PaymentEventRepositoryProtocol,
        payment_repository: PaymentRepositoryProtocol,
        refund_repository: RefundRepositoryProtocol,
        subscription_repository: SubscriptionRepositoryProtocol,
        plan_repository: PlanRepositoryProtocol,
        credit_repository: CreditRepositoryProtocol,
        payment_gateway: PaymentProviderProtocol,
        transaction_factory=None,
    ):
        self._event_repository = payment_event_repository
        self._payment_repository = payment_repository
        self._refund_repository = refund_repository
        self._payment_gateway = payment_gateway
        self._transaction_factory = transaction_factory or (lambda: db.transaction)
        self._activate = ActivateSubscription(
            subscription_repository=subscription_repository,
            plan_repository=plan_repository,
            credit_repository=credit_repository,
        )

    async def execute(self, payload: Dict) -> ProcessingResult:
        event_type = payload.get("event")
        obj = payload.get("object") or {}
        provider_id = obj.get("id")

        if not event_type or not provider_id:
            return ProcessingResult(ProcessingStatus.IGNORED, "missing event or object.id")

        external_event_id = f"{provider_id}:{event_type}"

        existing = self._event_repository.get_by_external_event_id(external_event_id)
        if existing is not None:
            return ProcessingResult(ProcessingStatus.ALREADY_PROCESSED, "event already processed")

        if event_type not in SUPPORTED_EVENTS:
            logger.info("Ignoring unsupported event %s (%s)", event_type, provider_id)
            return ProcessingResult(ProcessingStatus.IGNORED, f"unsupported event {event_type}")

        gateway_payment: Optional[GatewayPayment] = None
        if event_type == "payment.succeeded":
            gateway_payment = await self._verify_succeeded(provider_id, obj)

        try:
            with self._transaction_factory():
                result = self._process_in_transaction(
                    external_event_id=external_event_id,
                    event_type=event_type,
                    payload=payload,
                    provider_id=provider_id,
                    obj=obj,
                    gateway_payment=gateway_payment,
                )
                return result
        except UniqueProperty:
            logger.info("Unique constraint hit for %s, treating as already processed", external_event_id)
            return ProcessingResult(ProcessingStatus.ALREADY_PROCESSED, "concurrent duplicate")

    async def _verify_succeeded(self, provider_id: str, obj: Dict) -> GatewayPayment:
        """Перепроверка у провайдера: статус succeeded и совпадение суммы/валюты."""
        try:
            gateway_payment = await self._payment_gateway.get_payment(provider_id)
        except Exception as exc:
            logger.warning("Provider verification failed for %s: %s", provider_id, exc)
            raise ProviderError(f"Provider verification failed: {exc}") from exc

        if gateway_payment.status != "succeeded":
            raise WebhookError(f"Provider status is {gateway_payment.status!r}, not 'succeeded'")

        notif_amount = _obj_amount_kopecks(obj)
        if notif_amount is not None and notif_amount != gateway_payment.amount_kopecks:
            raise WebhookError("Amount mismatch between notification and provider")
        if obj.get("amount", {}).get("currency") not in (None, gateway_payment.currency):
            raise WebhookError("Currency mismatch between notification and provider")
        return gateway_payment

    def _process_in_transaction(
        self,
        *,
        external_event_id: str,
        event_type: str,
        payload: Dict,
        provider_id: str,
        obj: Dict,
        gateway_payment: Optional[GatewayPayment],
    ) -> ProcessingResult:
        # Повторная проверка идемпотентности уже внутри транзакции.
        existing = self._event_repository.get_by_external_event_id(external_event_id)
        if existing is not None:
            return ProcessingResult(ProcessingStatus.ALREADY_PROCESSED, "event already processed")

        now = utcnow()

        if event_type == "refund.succeeded":
            return self._handle_refund_succeeded(provider_id, external_event_id, payload, now)

        payment = self._payment_repository.get_by_provider_id(provider_id)
        if payment is None:
            payment = _reconstruct_payment(obj)
            if payment is None:
                return ProcessingResult(ProcessingStatus.IGNORED, "unknown payment")
            self._payment_repository.create(payment)

        if event_type == "payment.succeeded":
            if gateway_payment and (
                gateway_payment.amount_kopecks != payment.amount_kopecks
                or gateway_payment.currency != payment.currency
            ):
                return ProcessingResult(ProcessingStatus.REJECTED, "amount mismatch with stored payment")
            if not can_transition(payment.status, PaymentStatus.SUCCEEDED):
                return ProcessingResult(ProcessingStatus.IGNORED, f"payment {payment.status} -> SUCCEEDED")
            payment.status = transition(payment.status, PaymentStatus.SUCCEEDED)
            payment.updated_at = now
            self._payment_repository.save(payment)

            plan_code = (payment.metadata or {}).get("plan_code")
            if plan_code:
                activation = self._activate.execute(
                    user_id=payment.user_id,
                    plan_code=plan_code,
                    payment_uid=payment.uid,
                    now=now,
                )
                logger.info(
                    "Subscription %s activated for user %s (plan %s, credits +%s)",
                    activation.subscription.uid,
                    payment.user_id,
                    plan_code,
                    activation.credits_granted,
                )
            self._record_event(external_event_id, event_type, payload, now)
            return ProcessingResult(ProcessingStatus.PROCESSED, "payment succeeded")

        if event_type == "payment.canceled":
            if not can_transition(payment.status, PaymentStatus.FAILED):
                return ProcessingResult(ProcessingStatus.IGNORED, f"payment {payment.status} -> FAILED")
            payment.status = transition(payment.status, PaymentStatus.FAILED)
            payment.updated_at = now
            self._payment_repository.save(payment)
            self._record_event(external_event_id, event_type, payload, now)
            return ProcessingResult(ProcessingStatus.PROCESSED, "payment canceled")

        return ProcessingResult(ProcessingStatus.IGNORED, f"unsupported event {event_type}")

    def _handle_refund_succeeded(
        self,
        provider_id: str,
        external_event_id: str,
        payload: Dict,
        now: datetime,
    ) -> ProcessingResult:
        refund = self._refund_repository.get_by_provider_refund_id(provider_id)
        if refund is None:
            return ProcessingResult(ProcessingStatus.IGNORED, "unknown refund")
        refund.status = RefundStatus.SUCCEEDED
        self._refund_repository.save(refund)

        payment = self._payment_repository.get_by_uid(refund.payment_uid)
        if payment is not None and can_transition(payment.status, PaymentStatus.REFUNDED):
            payment.status = transition(payment.status, PaymentStatus.REFUNDED)
            payment.updated_at = now
            self._payment_repository.save(payment)

        self._record_event(external_event_id, event_type=payload.get("event", "refund.succeeded"), payload=payload, now=now)
        return ProcessingResult(ProcessingStatus.PROCESSED, "refund succeeded")

    def _record_event(self, external_event_id: str, event_type: str, payload: Dict, now: datetime) -> None:
        event = PaymentEvent(
            uid=str(uuid.uuid4()),
            provider="yookassa",
            external_event_id=external_event_id,
            event_type=event_type,
            payload=payload,
            processed_at=now,
        )
        self._event_repository.save(event)


def _obj_amount_kopecks(obj: Dict) -> Optional[int]:
    amount = obj.get("amount") or {}
    value = amount.get("value")
    if value is None:
        return None
    try:
        return value_to_kopecks(str(value))
    except ValueError:
        return None


def _reconstruct_payment(obj: Dict) -> Optional[Payment]:
    """Восстановление платежа по metadata, если записи в БД нет."""
    meta = obj.get("metadata") or {}
    user_id = meta.get("user_id")
    plan_code = meta.get("plan_code")
    amount_kopecks = _obj_amount_kopecks(obj)
    if not user_id or not plan_code or amount_kopecks is None:
        return None
    currency = (obj.get("amount") or {}).get("currency") or "RUB"
    return Payment(
        uid=str(uuid.uuid4()),
        user_id=user_id,
        amount_kopecks=amount_kopecks,
        currency=currency,
        status=PaymentStatus.PENDING,
        provider_payment_id=obj.get("id"),
        description=obj.get("description"),
        metadata=meta,
    )

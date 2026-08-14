"""
Layer: Application
Package: application.payments.refund_payment
Responsibility: Инициация возврата средств по оплаченному платежу.
"""
import uuid
from dataclasses import dataclass

from application.ports.payment_gateway import PaymentProviderProtocol
from application.ports.repositories import PaymentRepositoryProtocol, RefundRepositoryProtocol
from domain.exceptions import PaymentNotFoundError, ProviderError, DomainError
from domain.models import Refund
from domain.models.payment import PaymentStatus


@dataclass(frozen=True)
class RefundResult:
    refund_uid: str
    provider_refund_id: str
    status: str


class RefundPayment:
    def __init__(
        self,
        payment_repository: PaymentRepositoryProtocol,
        refund_repository: RefundRepositoryProtocol,
        payment_gateway: PaymentProviderProtocol,
    ):
        self._payment_repository = payment_repository
        self._refund_repository = refund_repository
        self._payment_gateway = payment_gateway

    async def execute(self, *, user_id: str, payment_uid: str) -> RefundResult:
        payment = self._payment_repository.get_by_uid(payment_uid)
        if payment is None or payment.user_id != user_id:
            raise PaymentNotFoundError("Payment not found")
        if payment.status != PaymentStatus.SUCCEEDED:
            raise DomainError("Only succeeded payments can be refunded")
        if not payment.provider_payment_id:
            raise ProviderError("Payment has no provider id")

        try:
            provider_refund_id = await self._payment_gateway.create_refund(
                provider_payment_id=payment.provider_payment_id,
                amount_kopecks=payment.amount_kopecks,
                currency=payment.currency,
                idempotency_key=str(uuid.uuid4()),
            )
        except Exception as exc:
            raise ProviderError(f"Refund provider error: {exc}") from exc

        refund = Refund(
            uid=str(uuid.uuid4()),
            payment_uid=payment.uid,
            amount_kopecks=payment.amount_kopecks,
            currency=payment.currency,
            status="PENDING",
            provider_refund_id=provider_refund_id,
        )
        self._refund_repository.create(refund)

        return RefundResult(
            refund_uid=refund.uid,
            provider_refund_id=refund.provider_refund_id or "",
            status=refund.status,
        )

"""
Layer: Application
Package: application.checkout.create_checkout
Responsibility: Создание платежа (чекаута) для пользователя.
"""
import uuid
from dataclasses import dataclass

from application.ports.payment_gateway import PaymentProviderProtocol
from application.ports.repositories import PaymentRepositoryProtocol, PlanRepositoryProtocol
from domain.exceptions import CheckoutError, PlanNotFoundError, ProviderConfigurationError
from domain.models import Payment
from domain.models.payment import PaymentStatus


@dataclass(frozen=True)
class CheckoutResult:
    payment_uid: str
    provider_payment_id: str
    confirmation_url: str


class CreateCheckout:
    def __init__(
        self,
        plan_repository: PlanRepositoryProtocol,
        payment_repository: PaymentRepositoryProtocol,
        payment_gateway: PaymentProviderProtocol,
    ):
        self._plan_repository = plan_repository
        self._payment_repository = payment_repository
        self._payment_gateway = payment_gateway

    async def execute(
        self,
        *,
        user_id: str,
        plan_code: str,
        return_url: str,
    ) -> CheckoutResult:
        plan = self._plan_repository.get_by_code(plan_code)
        if plan is None or not plan.is_active:
            raise PlanNotFoundError(f"Plan {plan_code!r} not found or inactive")

        if plan.price_kopecks == 0:
            raise CheckoutError(f"Plan {plan_code!r} is free, no checkout required")

        amount_kopecks = plan.price_kopecks
        currency = plan.currency
        description = f"{plan.name} ({plan.price_kopecks // 100} {currency}/мес)"
        metadata = {"user_id": user_id, "plan_code": plan.code}

        try:
            gateway_payment = await self._payment_gateway.create_payment(
                amount_kopecks=amount_kopecks,
                currency=currency,
                description=description,
                metadata=metadata,
                return_url=return_url,
                idempotency_key=str(uuid.uuid4()),
            )
        except ProviderConfigurationError:
            raise
        except Exception as exc:
            raise CheckoutError(f"Payment provider error: {exc}") from exc

        payment = Payment(
            uid=str(uuid.uuid4()),
            user_id=user_id,
            amount_kopecks=amount_kopecks,
            currency=currency,
            status=PaymentStatus.PENDING,
            provider_payment_id=gateway_payment.provider_payment_id,
            confirmation_url=gateway_payment.confirmation_url,
            description=description,
            metadata=metadata,
        )
        self._payment_repository.create(payment)

        return CheckoutResult(
            payment_uid=payment.uid,
            provider_payment_id=payment.provider_payment_id or "",
            confirmation_url=payment.confirmation_url or "",
        )

"""
Layer: Application
Package: application.ports.payment_gateway
Responsibility: Абстракция платёжного провайдера (ЮKassa и др.).
"""
from dataclasses import dataclass
from typing import Dict, Optional, Protocol


@dataclass(frozen=True)
class GatewayPayment:
    provider_payment_id: str
    status: str
    amount_kopecks: int
    currency: str
    confirmation_url: Optional[str] = None


class PaymentProviderProtocol(Protocol):
    async def create_payment(
        self,
        *,
        amount_kopecks: int,
        currency: str,
        description: str,
        metadata: Dict,
        return_url: str,
        idempotency_key: str,
    ) -> GatewayPayment: ...

    async def get_payment(self, provider_payment_id: str) -> GatewayPayment: ...

    async def create_refund(
        self,
        *,
        provider_payment_id: str,
        amount_kopecks: int,
        currency: str,
        idempotency_key: str,
    ) -> str: ...

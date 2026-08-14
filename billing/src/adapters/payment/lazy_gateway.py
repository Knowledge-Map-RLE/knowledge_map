"""
Layer: Interface Adapters
Package: adapters.payment.lazy_gateway
Responsibility: Ленивая инициализация платёжного провайдера.

Создаёт реальный gateway только при первом обращении к провайдеру.
Позволяет сервису стартовать и отвечать на health/plans даже когда
ключи ЮKassa не заданы; сам платёжный вызов вернёт 503
(ProviderConfigurationError).
"""
from typing import Dict

from application.ports.payment_gateway import GatewayPayment
from domain.exceptions import ProviderConfigurationError

DEFAULT_TIMEOUT_SECONDS = 30.0


class LazyPaymentGateway:
    """Прокси, реализующий PaymentProviderProtocol и создающий
    реальный адаптер при первом вызове метода (create_payment и т.д.)."""

    def __init__(self, *, shop_id: str, secret_key: str, api_url: str):
        self._shop_id = shop_id
        self._secret_key = secret_key
        self._api_url = api_url
        self._gateway = None

    def _ensure(self):
        if self._gateway is None:
            if not self._shop_id or not self._secret_key:
                raise ProviderConfigurationError(
                    "YOOKASSA_SHOP_ID / YOOKASSA_SECRET_KEY не заданы"
                )
            from adapters.payment.yookassa_gateway import YooKassaGateway

            self._gateway = YooKassaGateway(
                shop_id=self._shop_id,
                secret_key=self._secret_key,
                api_url=self._api_url,
                timeout=DEFAULT_TIMEOUT_SECONDS,
            )
        return self._gateway

    async def create_payment(
        self,
        *,
        amount_kopecks: int,
        currency: str,
        description: str,
        metadata: Dict,
        return_url: str,
        idempotency_key: str,
    ) -> GatewayPayment:
        return await self._ensure().create_payment(
            amount_kopecks=amount_kopecks,
            currency=currency,
            description=description,
            metadata=metadata,
            return_url=return_url,
            idempotency_key=idempotency_key,
        )

    async def get_payment(self, provider_payment_id: str) -> GatewayPayment:
        return await self._ensure().get_payment(provider_payment_id)

    async def create_refund(
        self,
        *,
        provider_payment_id: str,
        amount_kopecks: int,
        currency: str,
        idempotency_key: str,
    ) -> str:
        return await self._ensure().create_refund(
            provider_payment_id=provider_payment_id,
            amount_kopecks=amount_kopecks,
            currency=currency,
            idempotency_key=idempotency_key,
        )

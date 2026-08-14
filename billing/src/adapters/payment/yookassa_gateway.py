"""
Layer: Interface Adapters
Package: adapters.payment.yookassa_gateway
Responsibility: Адаптер платёжного провайдера ЮKassa (API v3).

Удовлетворяет PaymentProviderProtocol (application/ports/payment_gateway.py).
"""
import base64
from typing import Dict

import httpx

from application.ports.payment_gateway import GatewayPayment
from domain.exceptions import ProviderConfigurationError, ProviderError
from domain.rules.money import format_amount, value_to_kopecks

DEFAULT_TIMEOUT_SECONDS = 30.0


class YooKassaGateway:
    def __init__(
        self,
        *,
        shop_id: str,
        secret_key: str,
        api_url: str = "https://api.yookassa.ru/v3",
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ):
        if not shop_id or not secret_key:
            raise ProviderConfigurationError(
                "YOOKASSA_SHOP_ID / YOOKASSA_SECRET_KEY не заданы"
            )
        self._auth_header = "Basic " + base64.b64encode(
            f"{shop_id}:{secret_key}".encode("utf-8")
        ).decode("ascii")
        self._api_url = api_url.rstrip("/")
        self._timeout = timeout

    def _headers(self, idempotency_key: str | None = None) -> Dict[str, str]:
        headers = {
            "Authorization": self._auth_header,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if idempotency_key:
            headers["Idempotence-Key"] = idempotency_key
        return headers

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
        body = {
            "amount": {"value": format_amount(amount_kopecks), "currency": currency},
            "capture": True,
            "confirmation": {"type": "redirect", "return_url": return_url},
            "description": description,
            "metadata": metadata,
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._api_url}/payments",
                json=body,
                headers=self._headers(idempotency_key),
            )
        data = self._raise_for_status(response, context="create payment")
        amount = data.get("amount") or {}
        confirmation = data.get("confirmation") or {}
        return GatewayPayment(
            provider_payment_id=data.get("id", ""),
            status=data.get("status", ""),
            amount_kopecks=value_to_kopecks(amount.get("value", format_amount(amount_kopecks))),
            currency=amount.get("currency", currency),
            confirmation_url=confirmation.get("confirmation_url"),
        )

    async def get_payment(self, provider_payment_id: str) -> GatewayPayment:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(
                f"{self._api_url}/payments/{provider_payment_id}",
                headers=self._headers(),
            )
        data = self._raise_for_status(response, context="get payment")
        amount = data.get("amount") or {}
        return GatewayPayment(
            provider_payment_id=data.get("id", provider_payment_id),
            status=data.get("status", ""),
            amount_kopecks=value_to_kopecks(amount.get("value", "0.00")),
            currency=amount.get("currency", "RUB"),
        )

    async def create_refund(
        self,
        *,
        provider_payment_id: str,
        amount_kopecks: int,
        currency: str,
        idempotency_key: str,
    ) -> str:
        body = {
            "payment_id": provider_payment_id,
            "amount": {"value": format_amount(amount_kopecks), "currency": currency},
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._api_url}/refunds",
                json=body,
                headers=self._headers(idempotency_key),
            )
        data = self._raise_for_status(response, context="create refund")
        return data.get("id", "")

    @staticmethod
    def _raise_for_status(response: httpx.Response, *, context: str) -> Dict:
        if response.is_success:
            try:
                return response.json()
            except ValueError:
                raise ProviderError(f"Non-JSON response from YooKassa ({context})")
        detail = ""
        try:
            body = response.json()
            detail = body.get("description") or str(body)
        except ValueError:
            detail = response.text[:300]
        raise ProviderError(
            f"YooKassa {context} failed: HTTP {response.status_code} {detail}",
            code=response.status_code,
        )

"""
Layer: Frameworks & Drivers — Infrastructure
Package: infrastructure.billing_client.billing_client
Responsibility: HTTP-клиент к микросервису billing (порт 50058).

Принадлежит слою Infrastructure: использует httpx и конфигурацию для
межсервисного вызова. Авторизуется внутренним токеном (X-Internal-Token).
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx

from domain.exceptions import ExternalServiceError
from infrastructure.config import settings

logger = logging.getLogger(__name__)


class BillingClient:
    """Тонкий HTTP-клиент к billing-сервису (внутренние вызовы)."""

    def __init__(self, base_url: Optional[str] = None, internal_token: Optional[str] = None):
        self._base_url = (base_url or settings.BILLING_SERVICE_URL).rstrip("/")
        self._internal_token = internal_token if internal_token is not None else settings.INTERNAL_TOKEN

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self._internal_token:
            headers["X-Internal-Token"] = self._internal_token
        return headers

    def deduct_credits(
        self,
        *,
        user_id: str,
        amount: int,
        reference_id: str,
        description: Optional[str] = None,
    ) -> dict:
        """Списывает кредиты за AI-запрос (идемпотентно по reference_id)."""
        try:
            response = httpx.post(
                f"{self._base_url}/billing/credits/deduct",
                params={"user_id": user_id},
                headers=self._headers(),
                json={
                    "amount": amount,
                    "reference_id": reference_id,
                    "description": description,
                },
                timeout=30.0,
            )
        except httpx.HTTPError as exc:
            raise ExternalServiceError("billing", f"deduct request failed: {exc}") from exc
        if response.status_code == 402:
            return {"ok": False, "error": "not_enough_credits", "balance": None}
        if response.status_code >= 400:
            raise ExternalServiceError(
                "billing",
                f"deduct returned HTTP {response.status_code}: "
                f"{response.text[:300]}",
            )
        payload = response.json()
        return {"ok": True, "balance": payload.get("balance"), "error": None}

    def get_balance(self, *, user_id: str) -> int:
        """Текущий баланс кредитов пользователя (без создания аккаунта)."""
        try:
            response = httpx.get(
                f"{self._base_url}/billing/credits",
                params={"user_id": user_id},
                headers=self._headers(),
                timeout=15.0,
            )
        except httpx.HTTPError as exc:
            raise ExternalServiceError("billing", f"balance request failed: {exc}") from exc
        if response.status_code >= 400:
            raise ExternalServiceError(
                "billing",
                f"balance returned HTTP {response.status_code}: {response.text[:300]}",
            )
        return int(response.json().get("balance", 0))

    async def get_all_plans(self) -> list[dict]:
        """Список всех тарифов (публичный endpoint, токен не требуется).

        GET /billing/plans
        """
        headers = {"Content-Type": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(
                    f"{self._base_url}/billing/plans",
                    headers=headers,
                )
        except httpx.HTTPError as exc:
            raise ExternalServiceError("billing", f"plans request failed: {exc}") from exc
        if response.status_code >= 400:
            raise ExternalServiceError(
                "billing",
                f"plans returned HTTP {response.status_code}: {response.text[:300]}",
            )
        return response.json()

    async def get_user_subscription(self, user_id: str) -> dict | None:
        """Статус подписки пользователя.

        GET /billing/subscription?user_id=X (internal token)
        """
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(
                    f"{self._base_url}/billing/subscription",
                    params={"user_id": user_id},
                    headers=self._headers(),
                )
        except httpx.HTTPError as exc:
            raise ExternalServiceError("billing", f"subscription request failed: {exc}") from exc
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            raise ExternalServiceError(
                "billing",
                f"subscription returned HTTP {response.status_code}: {response.text[:300]}",
            )
        return response.json()

    async def get_user_payments(self, user_id: str, limit: int = 50) -> list[dict]:
        """Платежи отдельного пользователя.

        GET /billing/admin/payments?user_id=X (internal token)
        """
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(
                    f"{self._base_url}/billing/admin/payments",
                    params={"user_id": user_id, "limit": limit},
                    headers=self._headers(),
                )
        except httpx.HTTPError as exc:
            raise ExternalServiceError("billing", f"payments request failed: {exc}") from exc
        if response.status_code >= 400:
            raise ExternalServiceError(
                "billing",
                f"payments returned HTTP {response.status_code}: {response.text[:300]}",
            )
        return response.json().get("payments", [])

    async def get_all_payments(
        self,
        offset: int = 0,
        limit: int = 100,
        status: Optional[str] = None,
    ) -> list[dict]:
        """Все платежи сервиса с пагинацией и фильтром по статусу.

        GET /billing/admin/payments (internal token)
        """
        params = {"offset": offset, "limit": limit}
        if status:
            params["status"] = status
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(
                    f"{self._base_url}/billing/admin/payments",
                    params=params,
                    headers=self._headers(),
                )
        except httpx.HTTPError as exc:
            raise ExternalServiceError("billing", f"payments request failed: {exc}") from exc
        if response.status_code >= 400:
            raise ExternalServiceError(
                "billing",
                f"payments returned HTTP {response.status_code}: {response.text[:300]}",
            )
        return response.json().get("payments", [])

    async def get_all_subscriptions(self, status: Optional[str] = None) -> list[dict]:
        """Все подписки сервиса с фильтром по статусу.

        GET /billing/admin/subscriptions (internal token)
        """
        params: dict = {}
        if status:
            params["status"] = status
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(
                    f"{self._base_url}/billing/admin/subscriptions",
                    params=params,
                    headers=self._headers(),
                )
        except httpx.HTTPError as exc:
            raise ExternalServiceError("billing", f"subscriptions request failed: {exc}") from exc
        if response.status_code >= 400:
            raise ExternalServiceError(
                "billing",
                f"subscriptions returned HTTP {response.status_code}: {response.text[:300]}",
            )
        return response.json()

    async def get_admin_credit_transactions(
        self,
        user_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        """Все кредитные транзакции, опционально фильтр по пользователю.

        GET /billing/admin/credits/transactions (internal token)
        """
        params = {"limit": limit}
        if user_id:
            params["user_id"] = user_id
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(
                    f"{self._base_url}/billing/admin/credits/transactions",
                    params=params,
                    headers=self._headers(),
                )
        except httpx.HTTPError as exc:
            raise ExternalServiceError("billing", f"credit transactions request failed: {exc}") from exc
        if response.status_code >= 400:
            raise ExternalServiceError(
                "billing",
                f"credit transactions returned HTTP {response.status_code}: {response.text[:300]}",
            )
        return response.json().get("transactions", [])


billing_client = BillingClient()

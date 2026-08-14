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


billing_client = BillingClient()

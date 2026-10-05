"""Транспорт одной фоновой генерации Responses с чтением статуса и отменой."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re

import anyio
import httpx

logger = logging.getLogger(__name__)
PENDING = {"queued", "in_progress"}
TERMINAL = {"completed", "incomplete", "failed", "cancelled"}


class ResponseTaskError(Exception):
    def __init__(self, reason: str, response_id: str | None = None):
        super().__init__(reason)
        self.response_id = response_id


class BackgroundResponseTask:
    def __init__(self, client: httpx.AsyncClient, base_url: str, headers: dict,
                 timeout: float, *, poll_interval: float = 2.0):
        self.client, self.base_url, self.headers = client, base_url.rstrip("/"), headers
        self.timeout, self.poll_interval = timeout, poll_interval
        self.response_id: str | None = None
        self.last_response: dict = {}
        self.terminal = False
        self.request_sha256 = ""

    async def _request(self, method: str, path: str, *, payload=None) -> dict:
        attempts = 3 if method == "GET" else 1
        for attempt in range(attempts):
            try:
                response = await self.client.request(method, self.base_url + path,
                    headers=self.headers, **({"content": json.dumps(payload, ensure_ascii=False,
                        separators=(",", ":"), allow_nan=False).encode("utf-8")} if payload is not None else {}))
            except httpx.HTTPError as error:
                reason = "background_response_transport_error"
                retryable = True
            else:
                if response.status_code < 400:
                    try:
                        data = response.json()
                    except ValueError as error:
                        raise ResponseTaskError("background_response_invalid_json", self.response_id) from error
                    if not isinstance(data, dict):
                        raise ResponseTaskError("background_response_invalid_object", self.response_id)
                    return data
                # Сообщение провайдера может содержать запрос или секреты; сохраняем только статус.
                reason = f"background_response_http_{response.status_code}"
                retryable = response.status_code == 429 or response.status_code >= 500
            if not retryable or attempt + 1 == attempts:
                raise ResponseTaskError(reason, self.response_id)
            await asyncio.sleep(self.poll_interval * (attempt + 1))
        raise AssertionError("Unreachable request state")

    async def _cancel(self):
        # Отмена собственного фонового задания не создаёт новую генерацию.
        with anyio.CancelScope(shield=True):
            with anyio.move_on_after(10):
                try:
                    cancelled = await self._request("POST", f"/responses/{self.response_id}/cancel", payload={})
                    if cancelled.get("id") == self.response_id:
                        self.last_response = cancelled
                    logger.info("background_response cancelled response=%s status=%s",
                                self.response_id, cancelled.get("status") if cancelled.get("status") in TERMINAL else "unknown")
                except ResponseTaskError as error:
                    logger.error("background_response cancellation_failed response=%s reason=%s",
                                 self.response_id, str(error))

    async def run(self, payload: dict):
        previous_status = None
        request = payload | {"stream": False, "background": True, "store": True}
        self.request_sha256 = hashlib.sha256(json.dumps(request, ensure_ascii=False,
            separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()
        try:
            async with asyncio.timeout(self.timeout):
                response = await self._request("POST", "/responses",
                    payload=request)
                response_id = response.get("id")
                if not isinstance(response_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", response_id):
                    raise ResponseTaskError("background_response_invalid_id")
                self.response_id = response_id
                while True:
                    if response.get("id") != self.response_id:
                        raise ResponseTaskError("background_response_identity_changed", self.response_id)
                    self.last_response = response
                    status = response.get("status")
                    if status not in PENDING | TERMINAL:
                        raise ResponseTaskError("background_response_unknown_status", self.response_id)
                    if status != previous_status:
                        logger.info("background_response status response=%s status=%s", self.response_id, status)
                        previous_status = status
                    self.terminal = status in TERMINAL
                    yield response
                    if self.terminal:
                        return
                    await asyncio.sleep(self.poll_interval)
                    response = await self._request("GET", f"/responses/{self.response_id}")
        except TimeoutError as error:
            raise ResponseTaskError("background_response_timed_out", self.response_id) from error
        finally:
            if self.response_id and not self.terminal:
                await self._cancel()

"""Provider registry and OpenAI-compatible HTTP client.

The registry maps a model id to the upstream provider that serves it. Lookup order:

1. exact match against a provider's configured ``models`` list;
2. empty / ``default`` -> the default provider and model;
3. ``<provider-name>/<model>`` prefix match.

``list_models`` merges configured models with a live probe of each provider's
``GET /v1/models`` (cached briefly) so the UI always shows what is really loaded
(e.g. in LM Studio).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import httpx

from src.config import Provider, load_providers, settings

logger = logging.getLogger(__name__)


class ProviderError(Exception):
    """Raised when a provider is unknown or an upstream call fails."""


@dataclass
class ModelEntry:
    """A model exposed by ``GET /v1/models``."""

    id: str
    provider: str = ""
    configured: bool = False
    context_length: int = 0


@dataclass
class ProviderClient:
    """Thin OpenAI-compatible HTTP client for a single provider."""

    provider: Provider
    _client: httpx.AsyncClient = field(init=False, repr=False, default=None)

    def __post_init__(self) -> None:
        timeout = httpx.Timeout(settings.request_timeout, connect=settings.connect_timeout)
        self._client = httpx.AsyncClient(timeout=timeout)

    @property
    def base_url(self) -> str:
        return self.provider.base_url.rstrip("/")

    @property
    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.provider.api_key:
            headers["Authorization"] = f"Bearer {self.provider.api_key}"
        return headers

    async def chat_completions(self, model: str, payload: dict) -> tuple[httpx.Response, str]:
        """POST /chat/completions. Returns ``(response, resolved_model)``.

        The caller owns the response and must close it (``await response.aclose()``)
        once finished — this keeps streaming usable.
        """
        body = {**payload, "model": model}
        try:
            response = await self._client.post(
                f"{self.base_url}/chat/completions", json=body, headers=self._headers
            )
        except httpx.HTTPError as exc:
            raise ProviderError(
                f"Provider '{self.provider.name}' unreachable: {exc}"
            ) from exc
        if response.status_code >= 400:
            detail = (await response.aread()).decode("utf-8", errors="replace")[:500]
            raise ProviderError(
                f"Provider '{self.provider.name}' returned HTTP "
                f"{response.status_code}: {detail}"
            )
        return response, model

    async def list_models(self) -> list[ModelEntry]:
        entries: list[ModelEntry] = []
        try:
            response = await self._client.get(
                f"{self.base_url}/models", headers=self._headers
            )
            response.raise_for_status()
            data = response.json()
            for item in data.get("data", []):
                model_id = item.get("id")
                if model_id:
                    context_length = item.get("context_length") or settings.default_context_length
                    entries.append(
                        ModelEntry(
                            id=str(model_id),
                            provider=self.provider.name,
                            context_length=int(context_length),
                        )
                    )
        except httpx.HTTPError as exc:
            logger.warning("Model probe failed for '%s': %s", self.provider.name, exc)
        except (ValueError, KeyError, TypeError) as exc:
            logger.warning("Unexpected model payload from '%s': %s", self.provider.name, exc)
        return entries

    async def close(self) -> None:
        await self._client.aclose()


class Catalog:
    """Holds configured providers and resolves model -> provider."""

    def __init__(self) -> None:
        self._providers = load_providers()
        self._clients: dict[str, ProviderClient] = {}
        self._models_cache: tuple[float, list[ModelEntry]] | None = None

    @property
    def providers(self) -> list[Provider]:
        return self._providers

    def _client_for(self, provider: Provider) -> ProviderClient:
        client = self._clients.get(provider.name)
        if client is None:
            client = ProviderClient(provider)
            self._clients[provider.name] = client
        return client

    def resolve(self, model: str | None) -> tuple[ProviderClient, str]:
        """Map a model id to ``(ProviderClient, resolved_model)``."""
        requested = (model or "").strip()

        if requested and requested not in ("default",):
            for provider in self._providers:
                if requested in provider.models:
                    return self._client_for(provider), requested
            for provider in self._providers:
                if requested.startswith(provider.name + "/"):
                    return self._client_for(provider), requested
            raise ProviderError(f"Unknown model '{requested}'")

        default = self.default_provider()
        resolved = default.default_model or settings.default_model
        return self._client_for(default), resolved

    def default_provider(self) -> Provider:
        for provider in self._providers:
            if provider.name == settings.default_provider:
                return provider
        return self._providers[0]

    async def list_models(self) -> list[ModelEntry]:
        now = time.monotonic()
        if self._models_cache is not None and now - self._models_cache[0] < settings.models_cache_ttl:
            return self._models_cache[1]

        configured_ids = {
            model for provider in self._providers for model in provider.models
        }
        entries = [
            ModelEntry(
                id=model_id,
                provider=provider.name,
                configured=True,
                context_length=provider.context_length or settings.default_context_length,
            )
            for provider in self._providers
            for model_id in provider.models
        ]

        for provider in self._providers:
            client = self._client_for(provider)
            try:
                live = await client.list_models()
            except ProviderError as exc:
                logger.warning("Model probe skipped for '%s': %s", provider.name, exc)
                continue
            seen = {e.id for e in entries}
            for entry in live:
                if entry.id not in seen:
                    entries.append(entry)
                elif entry.id in configured_ids:
                    continue

        # Deduplicate by id, keep configured flag.
        dedup: dict[str, ModelEntry] = {}
        for entry in entries:
            existing = dedup.get(entry.id)
            if existing is None:
                dedup[entry.id] = entry
            elif entry.configured:
                dedup[entry.id] = entry
        result = sorted(dedup.values(), key=lambda e: (e.provider, e.id))
        self._models_cache = (now, result)
        return result

    async def close(self) -> None:
        for client in self._clients.values():
            await client.close()
        self._clients.clear()


catalog = Catalog()

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

import asyncio
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from src.config import Provider, load_providers, settings

logger = logging.getLogger(__name__)

RETRY_ATTEMPTS = 3
RETRY_BASE_DELAY = 2.0
RETRY_MAX_DELAY = 30.0


class ProviderError(Exception):
    """Raised when a provider is unknown or an upstream call fails."""


@dataclass
class ModelEntry:
    """A model exposed by ``GET /v1/models``."""

    id: str
    provider: str = ""
    configured: bool = False
    context_length: int = 0


def _sse_event(data: dict) -> str:
    """Serialize one server-sent event body as an SSE ``data:`` frame."""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _error_dict(message: str, model: str) -> dict:
    return {"error": {"type": "server_error", "message": message}}


@dataclass
class HttpProviderClient:
    """OpenAI-compatible HTTP client for non-SDK providers (LM Studio, custom)."""

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

    async def _request_streaming(self, body: dict) -> httpx.Response:
        url = f"{self.base_url}/chat/completions"
        headers = self._headers
        last_exc: Exception | None = None

        for attempt in range(RETRY_ATTEMPTS):
            try:
                response = await self._client.post(url, json=body, headers=headers)
            except httpx.HTTPError as exc:
                last_exc = exc
                delay = min(RETRY_BASE_DELAY * (2 ** attempt), RETRY_MAX_DELAY)
                logger.warning(
                    "Provider '%s' unreachable (attempt %d/%d): %s — retrying in %.1fs",
                    self.provider.name, attempt + 1, RETRY_ATTEMPTS, exc, delay,
                )
                await asyncio.sleep(delay)
                continue

            if response.status_code >= 500 or response.status_code == 429:
                detail = (await response.aread()).decode("utf-8", errors="replace")[:500]
                delay = min(RETRY_BASE_DELAY * (2 ** attempt), RETRY_MAX_DELAY)
                logger.warning(
                    "Provider '%s' HTTP %d (attempt %d/%d): %s — retrying in %.1fs",
                    self.provider.name, response.status_code, attempt + 1,
                    RETRY_ATTEMPTS, detail[:200], delay,
                )
                await response.aclose()
                await asyncio.sleep(delay)
                continue

            if response.status_code >= 400:
                detail = (await response.aread()).decode("utf-8", errors="replace")[:500]
                raise ProviderError(
                    f"Provider '{self.provider.name}' returned HTTP "
                    f"{response.status_code}: {detail}"
                )
            return response

        raise ProviderError(
            f"Provider '{self.provider.name}' unreachable after "
            f"{RETRY_ATTEMPTS} attempts: {last_exc}"
        )

    async def generate(self, model: str, req: dict) -> dict:
        """Single (non-streaming) completion → OpenAI-compatible response dict."""
        body = {**req, "model": model}
        response = await self._request_streaming(body)
        try:
            content = await response.aread()
        finally:
            await response.aclose()
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            text = content.decode("utf-8", errors="replace")
            raise ProviderError(
                f"Provider '{self.provider.name}' returned a non-JSON response: {text[:500]}"
            )

    async def stream(self, model: str, req: dict):
        """Streaming completion → async iterator of raw SSE bytes frames."""
        body = {**req, "model": model, "stream": True}
        response = await self._request_streaming(body)
        try:
            async for chunk in response.aiter_bytes():
                yield chunk
        finally:
            await response.aclose()

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


class LocalGGUFProviderClient:
    """Provider client running a local GGUF model via ``llama-cpp-python``.

    The model file is downloaded on first use from the HuggingFace Hub into
    ``MODEL_CACHE_DIR`` (``hf_hub_download``) and loaded lazily by llama.cpp.
    llama.cpp is blocking, so every call runs in a worker thread and generation
    is serialised with a lock (a loaded ``Llama`` instance is not thread-safe).

    Reasoning-style models (e.g. Qwen3.x "thinking") open the reply with a
    ``...`` block; it is stripped unless ``LOCAL_STRIP_REASONING=false``.
    """

    def __init__(self, provider: Provider) -> None:
        self.provider = provider
        self._llm: object | None = None
        self._load_lock = threading.Lock()
        self._gen_lock = threading.Lock()

    def _load_model(self):  # blocking; called from a worker thread
        from huggingface_hub import hf_hub_download
        from llama_cpp import Llama

        cache_dir = Path(settings.model_cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)
        model_path = hf_hub_download(
            repo_id=settings.hf_model_repo,
            filename=settings.hf_gguf_file,
            local_dir=cache_dir,
            token=settings.hugging_face_token or None,
        )
        logger.info(
            "Loading local GGUF model %s (context=%d, gpu_layers=%d)...",
            model_path, settings.local_context_length, settings.local_n_gpu_layers,
        )
        return Llama(
            model_path=str(model_path),
            n_ctx=settings.local_context_length,
            n_gpu_layers=settings.local_n_gpu_layers,
            verbose=False,
        )

    def _get_llm(self):  # blocking; called from a worker thread
        if self._llm is None:
            with self._load_lock:
                if self._llm is None:
                    self._llm = self._load_model()
        return self._llm

    def _completion(self, llm, req: dict) -> dict:
        kwargs: dict = {
            "messages": req.get("messages") or [],
            "max_tokens": req.get("max_tokens") or -1,
            "temperature": req.get("temperature"),
            "stream": False,
        }
        if kwargs["temperature"] is None:
            kwargs.pop("temperature")
        if kwargs["max_tokens"] == -1 or kwargs["max_tokens"] is None:
            kwargs["max_tokens"] = -1
        with self._gen_lock:
            return llm.create_chat_completion(**kwargs)

    @staticmethod
    def _strip_reasoning_block(text: str) -> str:
        """Drop the Qwen3.x ``...<thinking>...`` prefix from a reasoning reply."""
        if not text.startswith("..."):
            return text
        rest = text[3:]
        for marker in ("\n...\n", "\n..."):
            idx = rest.find(marker)
            if idx != -1:
                return rest[idx + len(marker):].lstrip(" \n")
        end = rest.find("...")
        if end != -1:
            return rest[end + 3:].lstrip(" \n")
        return rest.lstrip(" \n")

    def _to_openai(self, completion: dict, model: str) -> dict:
        choice = (completion.get("choices") or [{}])[0]
        content = (choice.get("message") or {}).get("content") or ""
        if settings.local_strip_reasoning:
            content = self._strip_reasoning_block(content)
        usage = completion.get("usage") or {}
        return {
            "id": completion.get("id") or "chatcmpl-local",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": choice.get("finish_reason", "stop"),
                }
            ],
            "usage": {
                "prompt_tokens": int(usage.get("prompt_tokens") or 0),
                "completion_tokens": int(usage.get("completion_tokens") or 0),
                "total_tokens": int(usage.get("total_tokens") or 0),
            },
        }

    async def generate(self, model: str, req: dict) -> dict:
        llm = await asyncio.to_thread(self._get_llm)
        completion = await asyncio.to_thread(self._completion, llm, req)
        return self._to_openai(completion, model)

    async def stream(self, model: str, req: dict):
        llm = await asyncio.to_thread(self._get_llm)
        completion = await asyncio.to_thread(self._completion, llm, req)
        data = self._to_openai(completion, model)
        message = data["choices"][0]["message"]

        yield _sse_event(
            {
                "id": data["id"],
                "object": "chat.completion.chunk",
                "created": data["created"],
                "model": model,
                "choices": [
                    {"index": 0, "delta": {"content": message["content"]}, "finish_reason": None}
                ],
            }
        )
        yield _sse_event(
            {
                "id": data["id"],
                "object": "chat.completion.chunk",
                "created": data["created"],
                "model": model,
                "choices": [
                    {"index": 0, "delta": {}, "finish_reason": data["choices"][0]["finish_reason"]}
                ],
                "usage": data["usage"],
            }
        )

    async def list_models(self) -> list[ModelEntry]:
        return [
            ModelEntry(id=m, provider=self.provider.name, configured=True, context_length=self.provider.context_length)
            for m in self.provider.models
        ]

    async def close(self) -> None:
        self._llm = None


class Catalog:
    """Holds configured providers and resolves model -> provider."""

    def __init__(self) -> None:
        self._providers = load_providers()
        self._clients: dict[str, object] = {}
        self._models_cache: tuple[float, list[ModelEntry]] | None = None

    @property
    def providers(self) -> list[Provider]:
        return self._providers

    def _client_for(self, provider: Provider) -> object:
        client = self._clients.get(provider.name)
        if client is None:
            if provider.use_local:
                client = LocalGGUFProviderClient(provider)
            else:
                client = HttpProviderClient(provider)
            self._clients[provider.name] = client
        return client

    def resolve(self, model: str | None) -> tuple[object, str]:
        """Map a model id to ``(client, resolved_model)``.

        The returned client exposes ``generate(model, req)`` and
        ``stream(model, req)`` regardless of the underlying implementation
        (raw HTTP or local GGUF).
        """
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

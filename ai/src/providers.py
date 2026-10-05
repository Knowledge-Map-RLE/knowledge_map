"""Provider registry and OpenAI-compatible HTTP client.

The catalog resolves a canonical profile from the shared model registry and
then maps that profile to the upstream provider. Exact model ids remain
accepted during migration, but unknown ids fail explicitly.

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
from contextlib import aclosing
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from src.config import Provider, load_providers, model_registry, settings
from src.response_tasks import BackgroundResponseTask, ResponseTaskError

logger = logging.getLogger(__name__)

RETRY_ATTEMPTS = 3
RETRY_BASE_DELAY = 2.0
RETRY_MAX_DELAY = 30.0


class ProviderError(Exception):
    """Raised when a provider is unknown or an upstream call fails."""

    def __init__(self, message: str, *, details: dict | None = None):
        super().__init__(message)
        self.details = details or {}


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
        last_error = "no response received"

        for attempt in range(RETRY_ATTEMPTS):
            try:
                response = await self._client.post(url, json=body, headers=headers)
            except httpx.HTTPError as exc:
                last_error = str(exc)
                delay = min(RETRY_BASE_DELAY * (2 ** attempt), RETRY_MAX_DELAY)
                logger.warning(
                    "Provider '%s' unreachable (attempt %d/%d): %s — retrying in %.1fs",
                    self.provider.name, attempt + 1, RETRY_ATTEMPTS, exc, delay,
                )
                await asyncio.sleep(delay)
                continue

            if response.status_code >= 500 or response.status_code == 429:
                detail = (await response.aread()).decode("utf-8", errors="replace")[:500]
                last_error = f"HTTP {response.status_code}: {detail}"
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
            f"{RETRY_ATTEMPTS} attempts: {last_error}"
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
        """Pass Cloud.ru SSE chunks through immediately and exactly once.

        The provider's ``[DONE]`` frame is consumed here; the public router
        writes its single terminal frame after this generator returns.  A
        retry is safe only before the first data frame, otherwise it could
        duplicate part of a completion.
        """
        body = {**req, "model": model, "stream": True}
        url = f"{self.base_url}/chat/completions"
        last_error = "no response received"

        try:
            async with asyncio.timeout(settings.request_timeout):
                for attempt in range(RETRY_ATTEMPTS):
                    emitted_frame = False
                    retryable = False
                    try:
                        async with self._client.stream(
                            "POST", url, json=body, headers=self._headers
                        ) as response:
                            if response.status_code >= 400:
                                detail = (await response.aread()).decode(
                                    "utf-8", errors="replace"
                                )[:500]
                                last_error = f"HTTP {response.status_code}: {detail}"
                                if response.status_code >= 500 or response.status_code == 429:
                                    retryable = True
                                else:
                                    raise ProviderError(
                                        f"Provider '{self.provider.name}' returned "
                                        f"HTTP {response.status_code}: {detail}"
                                    )
                            else:
                                async for raw_line in response.aiter_lines():
                                    line = raw_line.strip()
                                    if not line or not line.startswith("data:"):
                                        continue
                                    event_data = line.removeprefix("data:").strip()
                                    if event_data == "[DONE]":
                                        return
                                    emitted_frame = True
                                    yield f"data: {event_data}\n\n".encode("utf-8")
                                if emitted_frame:
                                    raise ProviderError(
                                        f"Provider '{self.provider.name}' closed an SSE stream "
                                        "without [DONE] after partial output"
                                    )
                                last_error = "SSE stream closed without data or [DONE]"
                                retryable = True
                    except httpx.HTTPError as exc:
                        if emitted_frame:
                            raise ProviderError(
                                f"Provider '{self.provider.name}' stream failed after partial output: {exc}"
                            ) from exc
                        last_error = str(exc)
                        retryable = True

                    if not retryable:
                        raise ProviderError(
                            f"Provider '{self.provider.name}' ended its SSE stream unexpectedly"
                        )
                    if attempt + 1 == RETRY_ATTEMPTS:
                        break
                    delay = min(RETRY_BASE_DELAY * (2 ** attempt), RETRY_MAX_DELAY)
                    logger.warning(
                        "Provider '%s' stream failed before output (attempt %d/%d): %s — retrying in %.1fs",
                        self.provider.name, attempt + 1, RETRY_ATTEMPTS, last_error, delay,
                    )
                    await asyncio.sleep(delay)
        except TimeoutError as exc:
            raise ProviderError(
                f"Provider '{self.provider.name}' stream timed out after "
                f"{settings.request_timeout} seconds"
            ) from exc

        raise ProviderError(
            f"Provider '{self.provider.name}' stream failed before output after "
            f"{RETRY_ATTEMPTS} attempts: {last_error}"
        )

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
                    context_length = (
                        item.get("max_model_len")
                        or item.get("context_length")
                        or settings.default_context_length
                    )
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


@dataclass
class OpenAIResponsesProviderClient:
    """OpenAI Responses API adapter exposed through the existing chat gateway.

    Chat Completions is the stable internal contract for Knowledge Map callers;
    GPT-6 reasoning runs through Responses so reasoning effort and streaming are
    mapped explicitly without changing local or OpenAI-compatible providers.
    """

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
        api_key = (self.provider.api_key or "").strip()
        if not api_key:
            raise ProviderError(
                f"Provider '{self.provider.name}' requires its configured API key "
                "environment variable"
            )
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def _payload(self, model: str, req: dict, *, stream: bool) -> dict:
        options = self.provider.generation_options.get(model, {})
        messages = req.get("messages") or []
        payload = {
            "model": model,
            # Preserve the full ordered conversation, including the DSL system
            # prompt and the entire unchunked article supplied by the caller.
            "input": [
                {"role": message["role"], "content": message["content"]}
                for message in messages
            ],
            "stream": stream,
        }
        reasoning_effort = options.get("reasoning_effort")
        if reasoning_effort:
            payload["reasoning"] = {"effort": reasoning_effort}
        max_output_tokens = (
            req.get("max_completion_tokens")
            or req.get("max_tokens")
            or options.get("max_tokens")
        )
        if max_output_tokens:
            payload["max_output_tokens"] = int(max_output_tokens)
        response_format = req.get("response_format")
        if response_format is not None:
            # Переносим контракт ответа клиента в формат Responses без подмены.
            if not isinstance(response_format, dict):
                raise ProviderError("Invalid response_format")
            format_type = response_format.get("type")
            if format_type == "json_schema":
                definition = response_format.get("json_schema")
                if (not isinstance(definition, dict)
                        or not isinstance(definition.get("name"), str)
                        or not isinstance(definition.get("schema"), dict)
                        or type(definition.get("strict", False)) is not bool):
                    raise ProviderError("Invalid JSON schema response_format")
                payload["text"] = {"format": {"type": "json_schema", **definition}}
            elif format_type in {"json_object", "text"}:
                payload["text"] = {"format": {"type": format_type}}
            else:
                raise ProviderError("Unsupported response_format")
        return payload

    @staticmethod
    def _usage_to_chat(usage: dict | None) -> dict:
        if not isinstance(usage, dict) or not usage:
            return {}
        prompt_tokens = int(usage.get("input_tokens") or 0)
        completion_tokens = int(usage.get("output_tokens") or 0)
        result = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": int(usage.get("total_tokens") or prompt_tokens + completion_tokens),
        }
        # Счётчики рассуждений и кэша нужны для честного учёта незавершённых вызовов.
        for upstream, internal, field_name in (
            ("output_tokens_details", "completion_tokens_details", "reasoning_tokens"),
            ("input_tokens_details", "prompt_tokens_details", "cached_tokens"),
        ):
            value = (usage.get(upstream) or {}).get(field_name)
            if type(value) is int and value >= 0:
                result[internal] = {field_name: value}
        return result

    @staticmethod
    def _output_text(response: dict) -> str:
        text = response.get("output_text")
        if isinstance(text, str):
            return text
        parts: list[str] = []
        for item in response.get("output") or []:
            for content in item.get("content") or []:
                if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                    parts.append(content["text"])
        return "".join(parts)

    @staticmethod
    def _error_message(payload: dict, fallback: str) -> str:
        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str) and message.strip():
                return message.strip()
        response = payload.get("response")
        if isinstance(response, dict):
            error = response.get("error")
            if isinstance(error, dict):
                message = error.get("message")
                if isinstance(message, str) and message.strip():
                    return message.strip()
        return fallback

    async def _post_json(self, payload: dict, *, retry: bool = True) -> dict:
        last_error = "no response received"
        attempts = RETRY_ATTEMPTS if retry else 1
        for attempt in range(attempts):
            try:
                response = await self._client.post(
                    f"{self.base_url}/responses", json=payload, headers=self._headers
                )
            except httpx.HTTPError as exc:
                last_error = str(exc)
                retryable = True
            else:
                if response.status_code >= 400:
                    detail = (await response.aread()).decode("utf-8", errors="replace")[:500]
                    last_error = f"HTTP {response.status_code}: {detail}"
                    retryable = response.status_code == 429 or response.status_code >= 500
                    await response.aclose()
                    if not retryable:
                        raise ProviderError(
                            f"Provider '{self.provider.name}' returned {last_error}"
                        )
                else:
                    try:
                        result = response.json()
                    except (ValueError, json.JSONDecodeError) as exc:
                        raise ProviderError(
                            f"Provider '{self.provider.name}' returned invalid JSON"
                        ) from exc
                    finally:
                        await response.aclose()
                    return result

            if attempt + 1 == attempts:
                break
            delay = min(RETRY_BASE_DELAY * (2 ** attempt), RETRY_MAX_DELAY)
            logger.warning(
                "Provider '%s' Responses request failed before output "
                "(attempt %d/%d): %s — retrying in %.1fs",
                self.provider.name, attempt + 1, attempts, last_error, delay,
            )
            await asyncio.sleep(delay)
        raise ProviderError(
            f"Provider '{self.provider.name}' Responses request failed after "
            f"{attempts} attempts: {last_error}"
        )

    async def generate(self, model: str, req: dict) -> dict:
        payload = self._payload(model, req, stream=False)
        response = await self._post_json(payload)
        status = response.get("status")
        if status != "completed":
            detail = response.get("incomplete_details") or response.get("error") or status
            raise ProviderError(
                f"Provider '{self.provider.name}' returned a non-completed response: {detail}"
            )
        return {
            "id": response.get("id") or "chatcmpl-openai",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": response.get("model") or model,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": self._output_text(response)},
                "finish_reason": "stop",
            }],
            "usage": self._usage_to_chat(response.get("usage")),
        }

    async def _stream_structured_response(self, model: str, req: dict):
        # Единственная фоновая генерация; GET читает состояние именно её id.
        task = BackgroundResponseTask(self._client, self.base_url, self._headers, settings.request_timeout)
        def common(response):
            frame = {"model": response.get("model") or model, "object": "chat.completion.chunk",
                     "created": int(time.time()), "upstream_transport": "responses_background",
                     "upstream_request_sha256": task.request_sha256}
            if task.response_id:
                frame["id"] = task.response_id
            if response.get("status") in {"queued", "in_progress", "completed", "incomplete", "failed", "cancelled"}:
                frame["upstream_status"] = response["status"]
            return frame
        try:
            async with aclosing(task.run(self._payload(model, req, stream=False))) as responses:
                async for response in responses:
                    if response.get("status") in {"queued", "in_progress"}:
                        yield _sse_event(common(response) | {"choices": []})
        except ResponseTaskError as error:
            # Счётчики отмены, если они доступны, не теряются из-за ошибки GET или таймаута.
            usage = self._usage_to_chat(task.last_response.get("usage"))
            yield _sse_event(common(task.last_response) | {"choices": [], "usage": usage})
            details = {"event_type": "response.failed", "transport_reason": str(error)}
            if task.response_id:
                details["response_id"] = task.response_id
            raise ProviderError(str(error), details=details) from error
        usage = self._usage_to_chat(response.get("usage"))
        frame = common(response)
        if response.get("status") != "completed":
            details = {"response_id": task.response_id, "event_type": "response.failed"}
            if response.get("status") == "incomplete":
                reason = (response.get("incomplete_details") or {}).get("reason")
                details.update(event_type="response.incomplete", incomplete_reason=(reason if reason in {
                    "max_output_tokens", "max_tokens", "content_filter", "steered"} else "unknown"))
            if usage:
                yield _sse_event(frame | {"choices": [], "usage": usage})
            raise ProviderError("OpenAI structured response did not complete", details=details)
        text = self._output_text(response)
        if not text.strip():
            raise ProviderError("OpenAI structured response is empty", details={"response_id": task.response_id})
        yield _sse_event(frame | {"choices": [{"index": 0, "delta": {"content": text},
                                                "finish_reason": None}]})
        yield _sse_event(frame | {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                                  "usage": usage})

    async def stream(self, model: str, req: dict):
        response_format = req.get("response_format") or {}
        if (response_format.get("type") == "json_schema"
                and (response_format.get("json_schema") or {}).get("strict") is True):
            # Это основной транспорт строгого JSON, а не повторный запрос после SSE-отказа.
            async with aclosing(self._stream_structured_response(model, req)) as frames:
                async for frame in frames:
                    yield frame
            return
        payload = self._payload(model, req, stream=True)
        headers = self._headers
        last_error = "stream ended before response.completed"
        for attempt in range(RETRY_ATTEMPTS):
            emitted_text = False
            retryable = False
            completed = False
            response_id = "chatcmpl-openai"
            response_model = model
            usage: dict = {}
            try:
                async with self._client.stream(
                    "POST", f"{self.base_url}/responses", json=payload, headers=headers
                ) as response:
                    if response.status_code >= 400:
                        detail = (await response.aread()).decode("utf-8", errors="replace")[:500]
                        last_error = f"HTTP {response.status_code}: {detail}"
                        retryable = response.status_code == 429 or response.status_code >= 500
                        if not retryable:
                            raise ProviderError(
                                f"Provider '{self.provider.name}' returned {last_error}"
                            )
                    else:
                        async for raw_line in response.aiter_lines():
                            line = raw_line.strip()
                            if not line.startswith("data:"):
                                continue
                            data = line.removeprefix("data:").strip()
                            if not data or data == "[DONE]":
                                continue
                            try:
                                event = json.loads(data)
                            except json.JSONDecodeError as exc:
                                raise ProviderError(
                                    f"Provider '{self.provider.name}' sent invalid SSE JSON"
                                ) from exc

                            event_type = event.get("type")
                            if event_type == "response.created":
                                upstream_response = event.get("response") or {}
                                response_id = upstream_response.get("id") or response_id
                                response_model = upstream_response.get("model") or model
                            elif event_type == "response.output_text.delta":
                                delta = event.get("delta")
                                if isinstance(delta, str) and delta:
                                    emitted_text = True
                                    yield _sse_event({
                                        "id": response_id,
                                        "object": "chat.completion.chunk",
                                        "created": int(time.time()),
                                        "model": response_model,
                                        "choices": [{
                                            "index": 0,
                                            "delta": {"content": delta},
                                            "finish_reason": None,
                                        }],
                                    })
                            elif event_type == "response.completed":
                                completed_response = event.get("response") or {}
                                if completed_response.get("status") != "completed":
                                    raise ProviderError(
                                        "OpenAI response did not complete: "
                                        + str(completed_response.get("incomplete_details")
                                              or completed_response.get("status"))
                                    )
                                response_id = completed_response.get("id") or response_id
                                response_model = completed_response.get("model") or response_model
                                usage = self._usage_to_chat(completed_response.get("usage"))
                                completed = True
                                yield _sse_event({
                                    "id": response_id,
                                    "object": "chat.completion.chunk",
                                    "created": int(time.time()),
                                    "model": response_model,
                                    "choices": [{
                                        "index": 0,
                                        "delta": {},
                                        "finish_reason": "stop",
                                    }],
                                    "usage": usage,
                                })
                                return
                            elif event_type in {"error", "response.failed", "response.incomplete"}:
                                failed_response = event.get("response") or {}
                                details = {"event_type": event_type}
                                if isinstance(failed_response.get("id"), str):
                                    details["response_id"] = failed_response["id"]
                                reason = (failed_response.get("incomplete_details") or {}).get("reason")
                                if event_type == "response.incomplete":
                                    details["incomplete_reason"] = (reason if reason in {
                                        "max_output_tokens", "max_tokens", "content_filter", "steered"
                                    } else "unknown")
                                failure_usage = self._usage_to_chat(failed_response.get("usage"))
                                if failure_usage:
                                    # Это счётчики отказа, а не завершающий успешный кадр.
                                    yield _sse_event({"id": failed_response.get("id") or response_id,
                                        "model": failed_response.get("model") or response_model,
                                        "object": "chat.completion.chunk", "choices": [],
                                        "usage": failure_usage})
                                raise ProviderError(
                                    f"OpenAI Responses stream failed: "
                                    f"{self._error_message(event, event_type or 'unknown error')}"
                                    + (f" ({details['incomplete_reason']})" if "incomplete_reason" in details else ""),
                                    details=details,
                                )
                        if not completed and not retryable:
                            raise ProviderError(
                                f"Provider '{self.provider.name}' closed its stream "
                                "without response.completed"
                            )
            except httpx.HTTPError as exc:
                if emitted_text:
                    raise ProviderError(
                        f"Provider '{self.provider.name}' stream failed after partial output: {exc}"
                    ) from exc
                last_error = str(exc)
                retryable = True

            if not retryable:
                break
            if attempt + 1 == RETRY_ATTEMPTS:
                break
            delay = min(RETRY_BASE_DELAY * (2 ** attempt), RETRY_MAX_DELAY)
            logger.warning(
                "Provider '%s' Responses stream failed before output "
                "(attempt %d/%d): %s — retrying in %.1fs",
                self.provider.name, attempt + 1, RETRY_ATTEMPTS, last_error, delay,
            )
            await asyncio.sleep(delay)
        raise ProviderError(
            f"Provider '{self.provider.name}' Responses stream failed after "
            f"{RETRY_ATTEMPTS} attempts: {last_error}"
        )

    async def list_models(self) -> list[ModelEntry]:
        return [
            ModelEntry(
                id=model,
                provider=self.provider.name,
                configured=True,
                context_length=self.provider.context_length or settings.default_context_length,
            )
            for model in self.provider.models
        ]

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
            elif provider.kind == "openai_responses":
                client = OpenAIResponsesProviderClient(provider)
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
        try:
            resolved_profile = model_registry.resolve(requested)
        except ValueError as exc:
            raise ProviderError(str(exc)) from exc
        provider = next(
            (item for item in self._providers if item.name == resolved_profile.provider.name),
            None,
        )
        if provider is None:
            raise ProviderError(
                f"Provider '{resolved_profile.provider.name}' for profile "
                f"'{resolved_profile.profile_name}' is not loaded"
            )
        return self._client_for(provider), resolved_profile.model_id

    def default_provider(self) -> Provider:
        try:
            active = model_registry.profile()
        except ValueError as exc:
            raise ProviderError(str(exc)) from exc
        for provider in self._providers:
            if provider.name == active.provider.name:
                return provider
        raise ProviderError(
            f"Provider '{active.provider.name}' for active profile "
            f"'{active.profile_name}' is not loaded"
        )

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

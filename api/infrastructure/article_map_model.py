"""Независимый транспорт текстовой LLM через штатный AI HTTP-сервис."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time

import httpx

from domain.article_maps import ArticleMapError, digest, fingerprint, require
from domain.knowledge_map_schema import dependency_review_json_schema
from infrastructure.config import model_registry, resolve_model_profile, settings

log = logging.getLogger(__name__)


class ArticleMapModelGateway:
    def __init__(self, *, output_schema: dict | None = None, strict_schema: bool = False,
                 json_object: bool = False):
        require(not json_object or output_schema is None, "Choose exactly one JSON response format")
        self.model = resolve_model_profile("article_extraction")
        profile = model_registry.profile(self.model)
        self.provider = profile.provider.name
        self.context_length = min(settings.LLM_CONTEXT_LENGTH, profile.profile.context_length)
        self.max_tokens = min(settings.LLM_MAX_TOKENS, profile.profile.max_tokens)
        self.timeout = settings.LLM_TIMEOUT
        self.reasoning_effort = profile.profile.reasoning_effort
        self.url = ("http://" + os.getenv("AI_MODEL_SERVICE_HOST", "127.0.0.1") + ":"
                    + os.getenv("AI_MODEL_SERVICE_PORT", "50059") + "/v1/chat/completions")
        self.last_call = {}
        self.last_response = ""
        self.output_schema = output_schema
        self.strict_schema = strict_schema
        self.json_object = json_object

    async def __call__(self, system: str, user: str) -> str:
        self.last_call, self.last_response = {}, ""
        body = {"model": self.model, "messages": [{"role": "system", "content": system},
                 {"role": "user", "content": user}], "stream": True,
                "stream_options": {"include_usage": True}, "max_completion_tokens": self.max_tokens}
        if self.output_schema is not None:
            # Обе текущие схемы закрыты и используют strict-режим провайдера;
            # старый контракт доступен только для совместимости транспорта.
            version = self.output_schema.get("properties", {}).get("schema_version", {}).get("const")
            schema_name = f"article_knowledge_map_v{version}" if version is not None else "article_knowledge_dependencies"
            body["response_format"] = {"type": "json_schema", "json_schema": {
                "name": schema_name, "schema": self.output_schema, "strict": self.strict_schema}}
        elif getattr(self, "json_object", False):
            # Разреженный словарь проверяется полной контекстной схемой на сервере.
            body["response_format"] = {"type": "json_object"}
        # Консервативная оценка повторяет действующий бюджет проекта, не режет статью.
        estimated_input = (len(json.dumps(body, ensure_ascii=False).encode("utf-8")) + 1025) // 2
        require(estimated_input + self.max_tokens + 2048 <= self.context_length,
                "Full article and complete output allowance exceed configured model context")
        started = time.monotonic()
        parts, usage = [], {}
        terminal, finish_reason = False, None
        first_token = None
        response_model = None
        response_id, upstream_failure, upstream_transport = None, None, None
        upstream_status, upstream_request_sha256 = None, None

        def capture_call():
            # Учёт сохраняется и при отказе: потраченные токены не исчезают из диагностики.
            self.last_response = "".join(parts)
            self.last_call = {"provider": self.provider, "model": self.model,
                              "request_body_sha256": fingerprint(body),
                              "response_sha256": digest(self.last_response),
                              "resolved_model": response_model,
                              "response_bytes": len("".join(parts).encode("utf-8")),
                              "reasoning_effort": self.reasoning_effort, "usage": usage,
                              "elapsed_seconds": round(time.monotonic() - started, 6),
                              "time_to_first_token_seconds": first_token,
                              "finish_reason": finish_reason, "sse_terminal_frame": terminal}
            if response_id:
                self.last_call["response_id"] = response_id
            if upstream_failure:
                self.last_call["upstream_failure"] = upstream_failure
            if upstream_transport:
                self.last_call["upstream_transport"] = upstream_transport
            if upstream_status:
                self.last_call["upstream_status"] = upstream_status
            if upstream_request_sha256:
                self.last_call["upstream_request_sha256"] = upstream_request_sha256
            if self.output_schema is not None:
                self.last_call["output_schema_sha256"] = fingerprint(self.output_schema)
        log.info("article_map_model request model=%s estimated_input=%s max_output=%s",
                 self.model, estimated_input, self.max_tokens)
        try:
            async with asyncio.timeout(self.timeout):
                async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout, connect=10)) as client:
                    async with client.stream("POST", self.url, json=body) as response:
                        if response.status_code >= 400:
                            # Ответ провайдера может содержать фрагмент запроса; в журнал его не пишем.
                            raise ArticleMapError(f"AI gateway HTTP {response.status_code}")
                        async for line in response.aiter_lines():
                            if not line.startswith("data:"):
                                continue
                            require(not terminal, "AI gateway sent data after its terminal frame")
                            raw = line.removeprefix("data:").strip()
                            if raw == "[DONE]":
                                terminal = True
                                # Дочитываем закрывающийся HTTP-поток, чтобы вложенные
                                # асинхронные генераторы завершились без отложенной очистки.
                                continue
                            try:
                                event = json.loads(raw)
                            except json.JSONDecodeError as exc:
                                raise ArticleMapError("AI gateway returned malformed SSE") from exc
                            if isinstance(event.get("id"), str):
                                response_id = event["id"]
                            if isinstance(event.get("model"), str):
                                response_model = event["model"]
                            if event.get("upstream_transport") in {"responses_json", "responses_background"}:
                                upstream_transport = event["upstream_transport"]
                            if event.get("upstream_status") in {"queued", "in_progress", "completed", "incomplete", "failed", "cancelled"}:
                                upstream_status = event["upstream_status"]
                            request_sha = event.get("upstream_request_sha256")
                            if isinstance(request_sha, str) and re.fullmatch(r"[a-f0-9]{64}", request_sha):
                                upstream_request_sha256 = request_sha
                            if isinstance(event.get("usage"), dict):
                                usage = event["usage"]
                            if "error" in event:
                                # Не сохраняем сообщение провайдера: оно может включать данные запроса.
                                details = event.get("upstream")
                                details = details if isinstance(details, dict) else {}
                                upstream_failure = {}
                                if details.get("event_type") in {"error", "response.failed", "response.incomplete"}:
                                    upstream_failure["event_type"] = details["event_type"]
                                if details.get("incomplete_reason") in {
                                    "max_output_tokens", "max_tokens", "content_filter", "steered", "unknown"}:
                                    upstream_failure["incomplete_reason"] = details["incomplete_reason"]
                                if response_id:
                                    upstream_failure["response_id"] = response_id
                                reason = details.get("transport_reason")
                                if isinstance(reason, str) and re.fullmatch(
                                    r"background_response_(?:http_[45][0-9]{2}|transport_error|invalid_json|invalid_object|invalid_id|identity_changed|unknown_status|timed_out)", reason):
                                    upstream_failure["transport_reason"] = reason
                                raise ArticleMapError("AI gateway reported an upstream error"
                                    + (f": {upstream_failure['incomplete_reason']}"
                                       if "incomplete_reason" in upstream_failure else
                                        f": {upstream_failure['transport_reason']}" if "transport_reason" in upstream_failure else ""))
                            for choice in event.get("choices", []):
                                content = choice.get("delta", {}).get("content")
                                if isinstance(content, str) and content:
                                    if first_token is None:
                                        first_token = time.monotonic() - started
                                    parts.append(content)
                                if choice.get("finish_reason") is not None:
                                    finish_reason = choice["finish_reason"]
        except TimeoutError as exc:
            capture_call()
            raise ArticleMapError("AI gateway timed out") from exc
        except BaseException:
            capture_call()
            raise
        capture_call()
        require(terminal and finish_reason == "stop", "Truncated or incomplete model response")
        raw = "".join(parts)
        require(bool(raw.strip()), "Model returned an empty response")
        log.info("article_map_model response model=%s resolved=%s elapsed=%.2f bytes=%s finish=%s usage=%s",
                 self.model, response_model, self.last_call["elapsed_seconds"],
                 self.last_call["response_bytes"], finish_reason, usage)
        return raw


class ArticleMapDependencyModelGateway(ArticleMapModelGateway):
    """Связывает идентификаторы с текстами конкретного проверяемого набора знаний."""

    def __init__(self):
        super().__init__(strict_schema=True)

    async def __call__(self, system: str, user: str) -> str:
        request = json.loads(user)
        schema = dependency_review_json_schema(request["knowledge_map"]["nodes"],
                                              request.get("dependency_target_keys"),
                                              request.get("accepted_dependencies"))
        self.output_schema = schema
        self.json_object = False
        self.strict_schema = True
        try:
            return await super().__call__(system, user)
        finally:
            if self.last_call:
                self.last_call["validation_schema_sha256"] = fingerprint(schema)

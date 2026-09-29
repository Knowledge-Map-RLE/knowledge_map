"""IO adapters for the core article pipeline; no extraction heuristics here."""
from __future__ import annotations
import json
import os
import logging
import time
import asyncio
from collections.abc import Callable
from infrastructure.config import model_registry, resolve_model_profile, settings

log = logging.getLogger(__name__)
CONTEXT_SAFETY_MARGIN = 2048
MIN_COMPLETION_TOKENS = 512
UTF8_BYTES_PER_ESTIMATED_TOKEN = 2
import grpc
import httpx
from google.protobuf.json_format import MessageToDict
from knowledge_contracts.validation import require
from utils.generated import nlp_pb2

class LinguisticGateway:
    async def __call__(self, text):
        target = os.getenv("NLP_SERVICE_HOST","127.0.0.1") + ":" + os.getenv("NLP_SERVICE_PORT","50055")
        async with grpc.aio.insecure_channel(target, options=[
            ("grpc.max_receive_message_length",256*1024*1024),
            ("grpc.max_send_message_length",256*1024*1024)]) as channel:
            analyze = channel.unary_unary('/nlp.NLPService/AnalyzeText',
                request_serializer=nlp_pb2.AnalyzeTextRequest.SerializeToString,
                response_deserializer=nlp_pb2.AnalyzeTextResponse.FromString)
            response = await analyze(
                nlp_pb2.AnalyzeTextRequest(text=text,enable_voting=False,preserve_source=True,
                    levels=[nlp_pb2.LEVEL_TOKENIZATION,nlp_pb2.LEVEL_MORPHOLOGY,nlp_pb2.LEVEL_SYNTAX]),
                timeout=600)
        require(response.success, "NLP analysis failed: " + response.message)
        return MessageToDict(response.document,preserving_proto_field_name=True,
                             always_print_fields_with_no_presence=True)

class SemanticGateway:
    # Production runs use an independent inference pass to audit claim-level
    # coverage after the initial DSL has passed structural validation.
    semantic_audit_enabled = True

    def __init__(self, model=None, on_first_token: Callable[[float], None] | None = None):
        self.model = resolve_model_profile("article_extraction", model or "")
        require(
            self.model == resolve_model_profile("article_extraction"),
            "Unconfigured article extraction model profile",
        )
        resolved_model = model_registry.profile(self.model)
        profile = resolved_model.profile
        self.provider = resolved_model.provider.name
        self.reasoning_effort = profile.reasoning_effort
        self.max_tokens = min(settings.LLM_MAX_TOKENS, profile.max_tokens)
        self.context_length = min(settings.LLM_CONTEXT_LENGTH, profile.context_length)
        require(0 < self.max_tokens < self.context_length, "Invalid article model token budget")
        self.url = "http://" + os.getenv("AI_MODEL_SERVICE_HOST","127.0.0.1") + ":" + os.getenv("AI_MODEL_SERVICE_PORT","50059") + "/v1/chat/completions"
        self.output_format = "dsl"
        self.last_call = {}
        self._on_first_token = on_first_token

    async def __call__(self, system, user):
        """Extract raw structural DSL through the AI gateway's SSE endpoint.

        Cloud.ru streams OpenAI-compatible chunks.  Reading them as they
        arrive both exposes time-to-first-token in the checkpoint and avoids
        holding an entire long completion in the gateway's memory.  The model
        is asked for DSL only; JSON schemas and JSON wrappers do not belong to
        this boundary.
        """
        body = {
            "model":self.model,"messages":[{"role":"system","content":system},{"role":"user","content":user}],
            "temperature":0,
            "max_completion_tokens":self.max_tokens,
            "stream":True,
            "stream_options":{"include_usage":True},
            # Documented Cloud.ru chat-template option.  It prevents a
            # reasoning preamble from consuming the DSL answer budget.
            "chat_template_kwargs":{"enable_thinking":False},
        }
        # LM Studio's OpenAI-compatible endpoint does not expose its tokenizer.
        # Treat each two UTF-8 bytes as one estimated token and reserve a large
        # margin for tokenizer variance and chat-template overhead. Counting one
        # byte as one token rejected valid Qwen requests whose actual prompt was
        # comfortably below the configured context length.
        input_bytes = len(json.dumps(body,ensure_ascii=False).encode("utf-8")) + 1024
        input_token_estimate = (
            input_bytes + UTF8_BYTES_PER_ESTIMATED_TOKEN - 1
        ) // UTF8_BYTES_PER_ESTIMATED_TOKEN
        # Keep the full configured output allowance when it fits. Large schema
        # catalogues and targeted feedback can leave less room, so reserve the
        # actual remaining context for output instead of rejecting an otherwise
        # valid request or silently exceeding the model's context.
        completion_tokens = min(
            self.max_tokens,
            self.context_length - input_token_estimate - CONTEXT_SAFETY_MARGIN,
        )
        require(
            completion_tokens >= MIN_COMPLETION_TOKENS,
            "Prompt and schema exceed the configured context budget "
            f"(estimated_input_tokens={input_token_estimate}, "
            f"requested_max_output_tokens={self.max_tokens}, "
            f"available_output_tokens={completion_tokens}, system_bytes={len(system.encode('utf-8'))}, "
            f"user_bytes={len(user.encode('utf-8'))}, context_length={self.context_length})",
        )
        body["max_completion_tokens"] = completion_tokens
        input_bytes = len(json.dumps(body,ensure_ascii=False).encode("utf-8")) + 1024
        input_token_estimate = (
            input_bytes + UTF8_BYTES_PER_ESTIMATED_TOKEN - 1
        ) // UTF8_BYTES_PER_ESTIMATED_TOKEN
        required_context_estimate = (
            input_token_estimate + completion_tokens + CONTEXT_SAFETY_MARGIN
        )
        require(
            required_context_estimate <= self.context_length,
            "Prompt and schema exceed the configured context budget "
            f"(estimated_context_tokens={required_context_estimate}, "
            f"estimated_input_tokens={input_token_estimate}, "
            f"system_bytes={len(system.encode('utf-8'))}, user_bytes={len(user.encode('utf-8'))}, "
            f"max_output_tokens={completion_tokens}, context_length={self.context_length})",
        )
        started = time.monotonic()
        log.info("article_model request model=%s estimated_input_tokens=%s "
                 "max_output_tokens=%s context=%s",
                 self.model,input_token_estimate,completion_tokens,self.context_length)
        parts: list[str] = []
        usage: dict = {}
        finish_reason = None
        first_token_seconds = None
        terminal_frame = False
        try:
            async with asyncio.timeout(settings.LLM_TIMEOUT):
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(settings.LLM_TIMEOUT, connect=10)
                ) as client:
                    async with client.stream("POST", self.url, json=body) as response:
                        if response.status_code >= 400:
                            detail = (await response.aread()).decode("utf-8", errors="replace")[:500]
                            raise OSError(f"AI gateway HTTP {response.status_code}: {detail}")
                        async for raw_line in response.aiter_lines():
                            line = raw_line.strip()
                            if not line or not line.startswith("data:"):
                                continue
                            event_data = line.removeprefix("data:").strip()
                            if event_data == "[DONE]":
                                terminal_frame = True
                                break
                            try:
                                event = json.loads(event_data)
                            except json.JSONDecodeError as exc:
                                raise OSError(
                                    "AI gateway returned invalid SSE JSON: " + event_data[:500]
                                ) from exc
                            if "error" in event:
                                raise OSError("AI gateway returned an error: " + str(event["error"]))
                            if isinstance(event.get("usage"), dict):
                                usage = event["usage"]
                            choices = event.get("choices") or []
                            if not choices:
                                continue
                            choice = choices[0]
                            delta = choice.get("delta") or {}
                            content = delta.get("content")
                            if isinstance(content, str) and content:
                                if first_token_seconds is None:
                                    first_token_seconds = round(time.monotonic() - started, 6)
                                    if self._on_first_token is not None:
                                        try:
                                            self._on_first_token(first_token_seconds)
                                        except Exception:  # observability must not break extraction
                                            log.exception("article_model first-token observer failed")
                                parts.append(content)
                            if choice.get("finish_reason") is not None:
                                finish_reason = choice["finish_reason"]
        except TimeoutError as exc:
            raise OSError(f"AI gateway timed out after {settings.LLM_TIMEOUT} seconds") from exc
        elapsed_seconds = round(time.monotonic() - started, 6)
        self.last_call = {
            "provider": self.provider,
            "model": self.model,
            "reasoning_effort": self.reasoning_effort,
            "max_completion_tokens": completion_tokens,
            "elapsed_seconds": elapsed_seconds,
            "time_to_first_token_seconds": first_token_seconds,
            "finish_reason": finish_reason,
            "usage": usage,
            "sse_terminal_frame": terminal_frame,
        }
        log.info("article_model response provider=%s model=%s reasoning_effort=%s "
                 "elapsed_seconds=%.2f finish=%s usage=%s",
                 self.provider,self.model,self.reasoning_effort,
                 elapsed_seconds,finish_reason,usage)
        require(terminal_frame, "AI gateway closed the SSE stream without a terminal frame")
        require(finish_reason == "stop", "Truncated or incomplete model response")
        dsl = "".join(parts)
        require(bool(dsl.strip()), "Article model returned an empty DSL response")
        return dsl

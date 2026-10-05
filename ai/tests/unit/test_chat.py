"""Tests for the OpenAI-compatible chat endpoint.

Uses a fake upstream provider so no real LLM is required.
"""

from __future__ import annotations

import json

import anyio
import pytest
from httpx import ASGITransport, AsyncClient, MockTransport, Response

from src.app import app
from src.config import Provider, settings
from src.providers import HttpProviderClient, OpenAIResponsesProviderClient


class FakeStream:
    """Mimics an httpx response over the SSE stream."""

    def __init__(self, chunks: list[bytes] | bytes, status: int = 200) -> None:
        if isinstance(chunks, (bytes, bytearray)):
            chunks = [bytes(chunks)]
        self._chunks = chunks
        self.status_code = status

    async def aiter_bytes(self):
        for chunk in self._chunks:
            yield chunk

    async def aread(self) -> bytes:
        return b"".join(self._chunks)

    async def aclose(self) -> None:
        return None


class FakeClient:
    """Fake ProviderClient that returns a canned OpenAI completion."""

    def __init__(self, stream: FakeStream) -> None:
        self._stream = stream
        self.last_payload: dict | None = None

    async def generate(self, model: str, req: dict) -> dict:
        self.last_payload = {**req, "model": model}
        content = (await self._stream.aread()).decode("utf-8")
        return json.loads(content)

    async def stream(self, model: str, req: dict):
        self.last_payload = {**req, "model": model, "stream": True}
        async for chunk in self._stream.aiter_bytes():
            yield chunk

    async def list_models(self):
        return []

    async def close(self):
        pass


def _plain_chunk(content: str) -> bytes:
    payload = {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 1,
        "model": "test-model",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
    }
    return json.dumps(payload).encode("utf-8")


def _sse_chunks(text: str) -> list[bytes]:
    chunks = []
    for token in text.split(" "):
        payload = {
            "id": "chatcmpl-test",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "test-model",
            "choices": [
                {"index": 0, "delta": {"content": token + " "}, "finish_reason": None}
            ],
        }
        chunks.append(("data: " + json.dumps(payload) + "\n\n").encode("utf-8"))
    return chunks


async def _post(path: str, json_body: dict | None = None) -> tuple[int, dict, str]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(path, json=json_body or {})
        body = (await response.aread()).decode("utf-8")
        return response.status_code, dict(response.headers), body


def _sync_post(path: str, json_body: dict | None = None) -> tuple[int, dict, str]:
    return anyio.run(_post, path, json_body)


@pytest.fixture
def fake_catalog(monkeypatch):
    client = FakeClient(FakeStream(_plain_chunk("hello world")))
    monkeypatch.setattr(
        "src.routers.chat.catalog.resolve", lambda model: (client, "test-model")
    )
    return client


def test_plain_completion(fake_catalog):
    status, _, body = _sync_post(
        "/v1/chat/completions",
        {
            "model": "qwen/qwen3-4b",
            "messages": [{"role": "user", "content": "Hi"}],
            "stream": False,
        },
    )
    assert status == 200
    assert json.loads(body)["choices"][0]["message"]["content"] == "hello world"


def test_system_prompt_injected(fake_catalog):
    _sync_post("/v1/chat/completions", {"messages": [{"role": "user", "content": "Hi"}]})
    messages = fake_catalog.last_payload["messages"]
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == settings.system_prompt
    assert fake_catalog.last_payload["model"] == "test-model"


def test_system_prompt_not_duplicated(fake_catalog):
    _sync_post(
        "/v1/chat/completions",
        {
            "messages": [
                {"role": "system", "content": "custom"},
                {"role": "user", "content": "Hi"},
            ]
        },
    )
    messages = fake_catalog.last_payload["messages"]
    assert messages[0]["content"] == "custom"
    assert len([m for m in messages if m["role"] == "system"]) == 1


def test_streaming_passthrough(monkeypatch):
    client = FakeClient(FakeStream(_sse_chunks("hello world")))
    monkeypatch.setattr(
        "src.routers.chat.catalog.resolve", lambda model: (client, "test-model")
    )
    status, headers, body = _sync_post(
        "/v1/chat/completions", {"messages": [{"role": "user", "content": "Hi"}], "stream": True}
    )
    assert status == 200
    assert headers["content-type"].startswith("text/event-stream")
    assert body.count("data: [DONE]") == 1
    assert "chat.completion.chunk" in body


def test_http_provider_streams_cloudru_sse_without_buffering():
    observed: dict = {}
    upstream_events = (
        b'data: {"id":"chatcmpl-test","object":"chat.completion.chunk",'
        b'"choices":[{"index":0,"delta":{"content":"B T4 B1"},'
        b'"finish_reason":null}]}\n\n'
        b'data: {"id":"chatcmpl-test","object":"chat.completion.chunk",'
        b'"choices":[{"index":0,"delta":{},"finish_reason":"stop"}],'
        b'"usage":{"completion_tokens":5}}\n\n'
        b'data: [DONE]\n\n'
    )

    async def upstream(request):
        observed["method"] = request.method
        observed["path"] = request.url.path
        observed["body"] = json.loads(request.content)
        return Response(200, headers={"content-type": "text/event-stream"}, content=upstream_events)

    async def collect():
        client = HttpProviderClient(
            Provider(name="cloudru", base_url="https://provider.example/v1", api_key="key")
        )
        await client._client.aclose()
        client._client = AsyncClient(transport=MockTransport(upstream))
        try:
            return [frame async for frame in client.stream("deepseek-ai/DeepSeek-V4-Flash", {
                "messages": [{"role": "user", "content": "DSL only"}],
                "max_completion_tokens": 64000,
                "stream_options": {"include_usage": True},
            })]
        finally:
            await client.close()

    frames = anyio.run(collect)
    forwarded = b"".join(frames).decode("utf-8")
    assert observed["method"] == "POST"
    assert observed["path"] == "/v1/chat/completions"
    assert observed["body"]["stream"] is True
    assert observed["body"]["stream_options"] == {"include_usage": True}
    assert observed["body"]["max_completion_tokens"] == 64000
    assert "B T4 B1" in forwarded
    assert "data: [DONE]" not in forwarded


def test_openai_responses_maps_full_conversation_and_reasoning_settings():
    observed: dict = {}

    async def upstream(request):
        observed["path"] = request.url.path
        observed["authorization"] = request.headers.get("authorization")
        observed["body"] = json.loads(request.content)
        return Response(200, json={
            "id": "resp-smoke",
            "status": "completed",
            "model": "gpt-6-luna",
            "output": [{"type": "message", "role": "assistant", "content": [
                {"type": "output_text", "text": "Привет! Чем могу помочь?"}
            ]}],
            "usage": {"input_tokens": 4, "output_tokens": 9, "total_tokens": 13},
        })

    async def run():
        client = OpenAIResponsesProviderClient(Provider(
            name="openai",
            base_url="https://api.openai.com/v1",
            kind="openai_responses",
            api_key="test-secret",
            models=["gpt-6-luna"],
            generation_options={"gpt-6-luna": {
                "reasoning_effort": "max", "max_tokens": 128000,
            }},
            context_length=1050000,
        ))
        await client._client.aclose()
        client._client = AsyncClient(transport=MockTransport(upstream))
        try:
            return await client.generate("gpt-6-luna", {
                "messages": [
                    {"role": "system", "content": "Complete DSL extraction prompt"},
                    {"role": "user", "content": "The entire article, without chunking."},
                ],
                "max_completion_tokens": 512,
                "temperature": 0,
            })
        finally:
            await client.close()

    result = anyio.run(run)
    assert observed["path"] == "/v1/responses"
    assert observed["authorization"] == "Bearer test-secret"
    assert observed["body"]["model"] == "gpt-6-luna"
    assert observed["body"]["input"] == [
        {"role": "system", "content": "Complete DSL extraction prompt"},
        {"role": "user", "content": "The entire article, without chunking."},
    ]
    assert observed["body"]["reasoning"] == {"effort": "max"}
    assert observed["body"]["max_output_tokens"] == 512
    assert "temperature" not in observed["body"]
    assert "text" not in observed["body"]
    assert result["choices"][0]["message"]["content"] == "Привет! Чем могу помочь?"
    assert result["usage"] == {
        "prompt_tokens": 4, "completion_tokens": 9, "total_tokens": 13,
    }


def test_openai_responses_preserves_json_schema_through_gateway(monkeypatch):
    definition = {"name": "article_knowledge_map_v4", "strict": False,
                  "schema": {"type": "object", "properties": {
                      "modality": {"type": ["string", "null"]}},
                      "required": ["modality"], "additionalProperties": False}}
    observed = {}

    async def upstream(request):
        observed.update(json.loads(request.content))
        return Response(200, json={"status": "completed", "output_text": '{"modality":null}'})

    async def run():
        client = OpenAIResponsesProviderClient(Provider(
            name="openai", base_url="https://provider.example/v1", api_key="test-secret"))
        await client._client.aclose()
        client._client = AsyncClient(transport=MockTransport(upstream))
        monkeypatch.setattr("src.routers.chat.catalog.resolve", lambda model: (client, "configured-model"))
        try:
            status, _, body = await _post("/v1/chat/completions", {
                "messages": [{"role": "user", "content": "Entire article"}],
                "response_format": {"type": "json_schema", "json_schema": definition},
            })
            assert status == 200
            assert json.loads(body)["choices"][0]["message"]["content"] == '{"modality":null}'
        finally:
            await client.close()

    anyio.run(run)
    assert observed["text"]["format"] == {"type": "json_schema", **definition}
    assert observed["input"][-1]["content"] == "Entire article"


@pytest.mark.parametrize("response_format", [{"type": "unknown"}, {"type": "json_schema"},
                                             {"type": "json_schema", "json_schema": {"name": "a", "schema": {}, "strict": "false"}}])
def test_openai_responses_rejects_invalid_schema_before_upstream(response_format):
    from src.providers import ProviderError
    client = OpenAIResponsesProviderClient.__new__(OpenAIResponsesProviderClient)
    client.provider = Provider(name="openai", base_url="https://provider.example/v1")
    with pytest.raises(ProviderError):
        client._payload("model", {"response_format": response_format}, stream=True)


def test_openai_responses_streams_text_deltas_as_chat_chunks():
    events = [
        {"type": "response.created", "response": {"id": "resp-stream", "model": "gpt-6-luna"}},
        {"type": "response.output_text.delta", "delta": "Привет"},
        {"type": "response.output_text.delta", "delta": "!"},
        {"type": "response.completed", "response": {
            "id": "resp-stream", "status": "completed", "model": "gpt-6-luna",
            "usage": {"input_tokens": 2, "output_tokens": 3, "total_tokens": 5},
        }},
    ]
    sse = "".join("data: " + json.dumps(event, ensure_ascii=False) + "\n\n" for event in events)

    async def upstream(request):
        return Response(200, headers={"content-type": "text/event-stream"}, content=sse)

    async def run():
        client = OpenAIResponsesProviderClient(Provider(
            name="openai", base_url="https://api.openai.com/v1", api_key="test-secret",
        ))
        await client._client.aclose()
        client._client = AsyncClient(transport=MockTransport(upstream))
        try:
            return [frame async for frame in client.stream("gpt-6-luna", {
                "messages": [{"role": "user", "content": "Привет"}],
            })]
        finally:
            await client.close()

    frames = [json.loads(frame.removeprefix("data: ").strip()) for frame in anyio.run(run)]
    assert [frame["choices"][0]["delta"].get("content") for frame in frames[:-1]] == [
        "Привет", "!",
    ]
    assert frames[-1]["choices"][0]["finish_reason"] == "stop"
    assert frames[-1]["usage"]["total_tokens"] == 5


def test_unknown_model(monkeypatch):
    from src.providers import ProviderError

    def _raise(model):
        raise ProviderError(f"Unknown model '{model}'")

    monkeypatch.setattr("src.routers.chat.catalog.resolve", _raise)
    status, _, body = _sync_post(
        "/v1/chat/completions", {"model": "nope/does-not-exist", "messages": []}
    )
    assert status == 400
    assert "error" in json.loads(body)


def test_health():
    transport = ASGITransport(app=app)
    async def _get():
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")
            return response.status_code, (await response.aread()).decode("utf-8")
    status, body = anyio.run(_get)
    assert status == 200
    assert json.loads(body)["status"] == "ok"


@pytest.mark.parametrize("reason,reported_usage", [
    ("max_output_tokens", {"input_tokens": 100, "output_tokens": 128000, "total_tokens": 128100,
                           "output_tokens_details": {"reasoning_tokens": 120000}}),
    ("content_filter", None),
])
def test_incomplete_response_preserves_usage_and_reason_without_success_or_retry(monkeypatch, reason, reported_usage):
    observed = []
    events = [
        {"type": "response.created", "response": {"id": "resp-incomplete", "model": "configured-model"}},
        {"type": "response.output_text.delta", "delta": '{"dependencies":'},
        {"type": "response.incomplete", "response": {
            "id": "resp-incomplete", "status": "incomplete", "model": "configured-model",
            "incomplete_details": {"reason": reason}, "usage": reported_usage}},
    ]
    async def upstream(request):
        observed.append(request)
        return Response(200, headers={"content-type": "text/event-stream"}, content="".join(
            "data: " + json.dumps(event) + "\n\n" for event in events))

    async def run():
        client = OpenAIResponsesProviderClient(Provider(
            name="openai", base_url="https://provider.example/v1", api_key="test-secret"))
        await client._client.aclose()
        client._client = AsyncClient(transport=MockTransport(upstream))
        monkeypatch.setattr("src.routers.chat.catalog.resolve", lambda model: (client, "configured-model"))
        try:
            return await _post("/v1/chat/completions", {"stream": True,
                "messages": [{"role": "user", "content": "Complete source"}]})
        finally:
            await client.close()
    status, _, body = anyio.run(run)
    assert status == 200 and len(observed) == 1 and body.count("data: [DONE]") == 1
    frames = [json.loads(line.removeprefix("data: ")) for line in body.splitlines()
              if line.startswith("data: ") and line != "data: [DONE]"]
    assert frames[-1]["upstream"]["incomplete_reason"] == reason
    assert frames[-1]["upstream"]["response_id"] == "resp-incomplete"
    assert not any(choice.get("finish_reason") == "stop" for frame in frames for choice in frame.get("choices", []))
    usage = [frame["usage"] for frame in frames if "usage" in frame]
    if reported_usage:
        assert usage[0]["completion_tokens"] == 128000
        assert usage[0]["completion_tokens_details"]["reasoning_tokens"] == 120000
    else:
        assert usage == []
    assert "test-secret" not in body


def test_unknown_usage_is_not_zero_usage():
    assert OpenAIResponsesProviderClient._usage_to_chat(None) == {}


@pytest.mark.parametrize("upstream_status", ["completed", "incomplete", "failed", "cancelled", None])
def test_strict_json_uses_atomic_response_and_requires_completed(monkeypatch, upstream_status):
    observed = []
    definition = {"name": "map", "strict": True, "schema": {"type": "object",
        "properties": {"label": {"type": "string"}}, "required": ["label"], "additionalProperties": False}}

    async def upstream(request):
        observed.append(json.loads(request.content))
        return Response(200, json={"id": "resp-atomic", "status": upstream_status,
            "model": "configured-model", "output_text": '{"label":"English knowledge"}',
            "incomplete_details": {"reason": "max_output_tokens"},
            "usage": {"input_tokens": 100, "output_tokens": 200, "total_tokens": 300,
                      "output_tokens_details": {"reasoning_tokens": 150}}})

    async def run():
        client = OpenAIResponsesProviderClient(Provider(
            name="openai", base_url="https://provider.example/v1", api_key="test-secret",
            generation_options={"configured-model": {"reasoning_effort": "max", "max_tokens": 128000}}))
        await client._client.aclose()
        client._client = AsyncClient(transport=MockTransport(upstream))
        monkeypatch.setattr("src.routers.chat.catalog.resolve", lambda model: (client, "configured-model"))
        try:
            return await _post("/v1/chat/completions", {"stream": True, "max_completion_tokens": 128000,
                "messages": [{"role": "system", "content": "Unchanged rules"},
                             {"role": "user", "content": "Entire article"}],
                "response_format": {"type": "json_schema", "json_schema": definition}})
        finally:
            await client.close()

    status, _, body = anyio.run(run)
    assert status == 200 and len([value for value in observed if "input" in value]) == 1 and body.count("data: [DONE]") == 1
    assert observed[0]["stream"] is False
    assert observed[0]["background"] is True and observed[0]["store"] is True
    assert observed[0]["model"] == "configured-model"
    assert observed[0]["input"] == [{"role": "system", "content": "Unchanged rules"},
                                     {"role": "user", "content": "Entire article"}]
    assert observed[0]["reasoning"] == {"effort": "max"}
    assert observed[0]["max_output_tokens"] == 128000
    assert observed[0]["text"]["format"] == {"type": "json_schema", **definition}
    frames = [json.loads(line.removeprefix("data: ")) for line in body.splitlines()
              if line.startswith("data: ") and line != "data: [DONE]"]
    assert frames[0]["usage"] if upstream_status != "completed" else frames[-1]["usage"]
    usage = next(frame["usage"] for frame in frames if "usage" in frame)
    assert usage["total_tokens"] == 300
    assert usage["completion_tokens_details"]["reasoning_tokens"] == 150
    if upstream_status == "completed":
        assert frames[0]["choices"][0]["delta"]["content"] == '{"label":"English knowledge"}'
        assert frames[-1]["choices"][0]["finish_reason"] == "stop"
        assert frames[-1]["upstream_transport"] == "responses_background"
    else:
        assert not any(choice.get("delta", {}).get("content") for frame in frames for choice in frame.get("choices", []))
        assert not any(choice.get("finish_reason") == "stop" for frame in frames for choice in frame.get("choices", []))
        assert frames[-1]["upstream"]["response_id"] == "resp-atomic"
        if upstream_status == "incomplete":
            assert frames[-1]["upstream"]["incomplete_reason"] == "max_output_tokens"
    assert "test-secret" not in body


def test_strict_json_does_not_repeat_post_on_transport_failure():
    from src.providers import ProviderError
    observed = []

    async def upstream(request):
        observed.append(request)
        return Response(500, json={"error": {"message": "transport unavailable"}})

    async def run():
        client = OpenAIResponsesProviderClient(Provider(
            name="openai", base_url="https://provider.example/v1", api_key="test-secret"))
        await client._client.aclose()
        client._client = AsyncClient(transport=MockTransport(upstream))
        try:
            with pytest.raises(ProviderError):
                return [frame async for frame in client.stream("model", {
                    "messages": [{"role": "user", "content": "Entire article"}],
                    "response_format": {"type": "json_schema", "json_schema": {
                        "name": "map", "strict": True, "schema": {"type": "object"}}}})]
        finally:
            await client.close()
    anyio.run(run)
    assert len(observed) == 1


def test_background_gateway_polls_same_id_and_does_not_publish_pending_text(monkeypatch):
    from src.response_tasks import BackgroundResponseTask
    observed = []
    statuses = iter(["queued", "in_progress", "completed"])
    def upstream(request):
        observed.append((request.method, request.url.path))
        status = next(statuses)
        return Response(200, json={"id": "resp-background", "model": "configured-model", "status": status,
            "output_text": '{"label":"English knowledge"}' if status == "completed" else "private pending text",
            "usage": {"input_tokens": 100, "output_tokens": 200, "total_tokens": 300} if status == "completed" else None})
    async def run():
        client = OpenAIResponsesProviderClient(Provider(
            name="openai", base_url="https://provider.example/v1", api_key="test-secret"))
        await client._client.aclose()
        client._client = AsyncClient(transport=MockTransport(upstream))
        monkeypatch.setattr("src.routers.chat.catalog.resolve", lambda model: (client, "configured-model"))
        monkeypatch.setattr("src.providers.BackgroundResponseTask", lambda *args: BackgroundResponseTask(*args, poll_interval=0))
        try:
            return await _post("/v1/chat/completions", {"stream": True,
                "messages": [{"role": "user", "content": "Entire article"}],
                "response_format": {"type": "json_schema", "json_schema": {
                    "name": "map", "strict": True, "schema": {"type": "object"}}}})
        finally:
            await client.close()
    status, _, body = anyio.run(run)
    assert status == 200 and "private pending text" not in body and "test-secret" not in body
    assert observed == [("POST", "/v1/responses"), ("GET", "/v1/responses/resp-background"),
                        ("GET", "/v1/responses/resp-background")]
    frames = [json.loads(line.removeprefix("data: ")) for line in body.splitlines()
              if line.startswith("data: ") and line != "data: [DONE]"]
    assert [frame.get("upstream_status") for frame in frames[:2]] == ["queued", "in_progress"]
    assert frames[-1]["choices"][0]["finish_reason"] == "stop"
    assert frames[-1]["usage"]["total_tokens"] == 300
    assert frames[-1]["upstream_request_sha256"]


@pytest.mark.parametrize("disconnect_at", ["send", "poll"])
def test_background_response_is_cancelled_before_asgi_disconnect_returns(monkeypatch, disconnect_at):
    from src.response_tasks import BackgroundResponseTask
    from src.routers.chat import chat_completions
    from src.schemas import ChatCompletionRequest

    observed = []

    async def run():
        disconnected = anyio.Event()

        async def upstream(request):
            observed.append((request.method, request.url.path))
            if request.url.path.endswith("/cancel"):
                return Response(200, json={"id": "resp-owned", "status": "cancelled"})
            if request.method == "GET":
                disconnected.set()
                await anyio.sleep_forever()
            return Response(200, json={"id": "resp-owned", "status": "queued"})

        client = OpenAIResponsesProviderClient(Provider(
            name="openai", base_url="https://provider.example/v1", api_key="test-secret"))
        await client._client.aclose()
        client._client = AsyncClient(transport=MockTransport(upstream))
        monkeypatch.setattr("src.routers.chat.catalog.resolve", lambda model: (client, "configured-model"))
        monkeypatch.setattr("src.providers.BackgroundResponseTask",
                            lambda *args: BackgroundResponseTask(*args, poll_interval=0))
        response = await chat_completions(ChatCompletionRequest.model_validate({
            "stream": True, "messages": [{"role": "user", "content": "Full article"}],
            "response_format": {"type": "json_schema", "json_schema": {
                "name": "map", "strict": True, "schema": {"type": "object"}}}}))

        async def receive():
            await disconnected.wait()
            return {"type": "http.disconnect"}

        async def send(message):
            if message["type"] == "http.response.body" and disconnect_at == "send":
                disconnected.set()
                await anyio.sleep_forever()

        try:
            with anyio.fail_after(1):
                await response({"type": "http", "asgi": {"spec_version": "2.3"}}, receive, send)
            # Проверяем отмену до выхода из ASGI, а не отложенную сборку генераторов.
            assert observed[-1] == ("POST", "/v1/responses/resp-owned/cancel")
            assert observed.count(("POST", "/v1/responses")) == 1
            assert observed.count(("POST", "/v1/responses/resp-owned/cancel")) == 1
        finally:
            await response.body_iterator.aclose()
            await client.close()

    anyio.run(run)

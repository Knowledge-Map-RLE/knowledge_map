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
    assert result["choices"][0]["message"]["content"] == "Привет! Чем могу помочь?"
    assert result["usage"] == {
        "prompt_tokens": 4, "completion_tokens": 9, "total_tokens": 13,
    }


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

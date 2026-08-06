"""Tests for the OpenAI-compatible chat endpoint.

Uses a fake upstream provider so no real LLM is required.
"""

from __future__ import annotations

import json

import anyio
import pytest
from httpx import ASGITransport, AsyncClient

from src.app import app
from src.config import settings


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

    async def chat_completions(self, model: str, payload: dict):
        self.last_payload = payload
        return self._stream, model


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
    chunks.append(b"data: [DONE]\n\n")
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
    assert "data: [DONE]" in body
    assert "chat.completion.chunk" in body


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

"""Проверки единственной генерации, идентичности ответа и отмены фонового задания."""
import asyncio
import hashlib
from contextlib import aclosing

import anyio
import httpx
import pytest

from src.response_tasks import BackgroundResponseTask, ResponseTaskError


def test_background_statuses_preserve_one_generation_and_exact_input():
    observed = []
    payload = {"model": "configured-model", "input": [{"role": "user", "content": "Entire article"}],
               "reasoning": {"effort": "max"}, "max_output_tokens": 128000,
               "text": {"format": {"type": "json_schema", "strict": True}}}
    statuses = iter(["queued", "in_progress", "completed"])
    def upstream(request):
        observed.append(request)
        return httpx.Response(200, json={"id": "resp-original", "status": next(statuses), "output_text": "{}"})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as client:
            task = BackgroundResponseTask(client, "https://provider.example/v1", {}, 5, poll_interval=0)
            return [response async for response in task.run(payload)], task.request_sha256
    result, request_sha = anyio.run(run)
    assert [r["status"] for r in result] == ["queued", "in_progress", "completed"]
    assert [r.method for r in observed] == ["POST", "GET", "GET"]
    import json
    assert json.loads(observed[0].content) == payload | {"stream": False, "background": True, "store": True}
    assert request_sha == hashlib.sha256(observed[0].content).hexdigest()
    assert all(r.url.path == "/v1/responses/resp-original" for r in observed[1:])


@pytest.mark.parametrize("failure", ["identity", "unknown_status", "transport", "timeout", "consumer_close"])
def test_background_failure_cancels_own_task_without_another_generation(failure):
    observed = []
    async def upstream(request):
        observed.append((request.method, request.url.path))
        if request.url.path.endswith("/cancel"):
            return httpx.Response(200, json={"id": "resp-original", "status": "cancelled"})
        if request.method == "POST":
            return httpx.Response(200, json={"id": "resp-original", "status": "queued"})
        if failure == "identity":
            return httpx.Response(200, json={"id": "resp-foreign", "status": "completed"})
        if failure == "unknown_status":
            return httpx.Response(200, json={"id": "resp-original", "status": "unexpected"})
        if failure == "transport":
            return httpx.Response(503)
        await anyio.sleep(1)
        return httpx.Response(200, json={"id": "resp-original", "status": "completed"})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as client:
            task = BackgroundResponseTask(client, "https://provider.example/v1", {}, .03, poll_interval=0)
            if failure == "consumer_close":
                async with aclosing(task.run({})) as responses:
                    assert (await anext(responses))["status"] == "queued"
            else:
                with pytest.raises(ResponseTaskError):
                    async for _ in task.run({}):
                        pass
            assert task.last_response["status"] == "cancelled"
    anyio.run(run)
    assert observed.count(("POST", "/v1/responses")) == 1
    assert observed.count(("POST", "/v1/responses/resp-original/cancel")) == 1
    assert not any("resp-foreign" in path for _, path in observed)


def test_background_cancellation_propagates_and_cancels_remote_response():
    observed = []
    async def upstream(request):
        observed.append((request.method, request.url.path))
        if request.url.path.endswith("/cancel"):
            return httpx.Response(200, json={"id": "resp-original", "status": "cancelled"})
        if request.method == "GET":
            await anyio.sleep(1)
        return httpx.Response(200, json={"id": "resp-original", "status": "queued"})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as client:
            remote = BackgroundResponseTask(client, "https://provider.example/v1", {}, 5, poll_interval=0)
            async def consume():
                async with aclosing(remote.run({})) as responses:
                    async for _ in responses:
                        pass
            consumer = asyncio.create_task(consume())
            await anyio.sleep(.02)
            consumer.cancel()
            with pytest.raises(asyncio.CancelledError):
                await consumer
            assert remote.last_response["status"] == "cancelled"
    anyio.run(run)
    assert observed.count(("POST", "/v1/responses")) == 1
    assert observed.count(("POST", "/v1/responses/resp-original/cancel")) == 1


def test_transient_get_failure_retries_same_response_only():
    observed = []
    def upstream(request):
        observed.append((request.method, request.url.path))
        if request.method == "POST":
            return httpx.Response(200, json={"id": "resp-original", "status": "queued"})
        if len(observed) == 2:
            return httpx.Response(429)
        return httpx.Response(200, json={"id": "resp-original", "status": "completed"})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as client:
            task = BackgroundResponseTask(client, "https://provider.example/v1", {}, 5, poll_interval=0)
            return [response async for response in task.run({})]
    assert anyio.run(run)[-1]["status"] == "completed"
    assert observed == [("POST", "/v1/responses"), ("GET", "/v1/responses/resp-original"),
                        ("GET", "/v1/responses/resp-original")]

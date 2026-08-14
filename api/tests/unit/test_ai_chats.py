"""Юнит-тесты use cases персистентных AI-чатов (fakes, без Neo4j/сети)."""
import asyncio
import uuid
from datetime import datetime

import pytest

from application.ai_chats.create_chat import create_ai_chat
from application.ai_chats.get_chat import get_ai_chat, get_ai_chat_messages
from application.ai_chats.list_chats import list_ai_chats
from application.ai_chats.send_message import send_ai_message_stream
from application.ai_chats.usage_summary import usage_summary
from domain.exceptions import AuthorizationFailed, NotFoundError
from domain.models.ai_chat import AIChat, AIMessage, AIUsage


async def _aiter(agen):
    return [event async for event in agen]


def _collect(agen):
    return asyncio.run(_aiter(agen))


class FakeAIChatRepository:
    def __init__(self):
        self.chats = {}
        self.messages = {}
        self.usages = []

    def get_chat(self, chat_uid):
        return self.chats.get(chat_uid)

    def list_chats(self, user_uid, limit=50):
        return [c for c in self.chats.values() if c.user_uid == user_uid][:limit]

    def create_chat(self, chat):
        self.chats[chat.uid] = chat
        return chat

    def touch_chat(self, chat_uid):
        pass

    def list_messages(self, chat_uid, limit=100):
        return sorted(self.messages.get(chat_uid, []), key=lambda m: m.order)[:limit]

    def add_message(self, message):
        self.messages.setdefault(message.chat_uid, []).append(message)
        return message

    def save_usage(self, usage):
        self.usages.append(usage)
        return usage

    def get_usage_by_provider_id(self, provider_request_id):
        for u in self.usages:
            if u.provider_request_id == provider_request_id:
                return u
        return None

    def list_usage_for_chat(self, chat_uid, limit=100):
        return [u for u in self.usages if u.chat_uid == chat_uid][:limit]

    def list_usage_for_user(self, user_uid, since=None, until=None, limit=100):
        result = [u for u in self.usages if u.user_uid == user_uid]
        if since:
            result = [u for u in result if u.created_at.timestamp() >= since]
        return result[:limit]


class FakeTokenizer:
    def estimate_messages_usage(self, messages, max_output_tokens=None):
        total = sum(len(m.get("content", "").split()) for m in messages) + len(messages)
        return {
            "estimated_input_tokens": total,
            "estimated_output_tokens": max_output_tokens or 1500,
        }

    def count_tokens(self, text):
        return len(text.split()) + 1

    def count_messages_tokens(self, messages):
        return sum(len(m.get("content", "").split()) for m in messages) + len(messages)


class FakeGateway:
    def __init__(self, chunks=("Hello", " ", "world"), usage=None):
        self.chunks = chunks
        self.usage = usage or {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
        }
        self.streamed = False

    async def stream_chat_completions(self, messages, model="", **kwargs):
        self.streamed = True
        payload = {"id": f"resp-{uuid.uuid4()}", "usage": self.usage}
        yield '{"choices": []}'  # не парсится в delta
        yield _sse_payload(payload)
        for chunk in self.chunks:
            yield _sse_payload({"choices": [{"delta": {"content": chunk}}]})
        yield "[DONE]"


class FakeBilling:
    def __init__(self):
        self.calls = []

    def deduct_credits(self, *, user_id, amount, reference_id, description=None):
        self.calls.append(
            {"user_id": user_id, "amount": amount, "reference_id": reference_id}
        )
        return {"ok": True, "balance": 100 - amount, "error": None}


def _sse_payload(data: dict) -> str:
    import json

    return json.dumps(data)


@pytest.fixture
def repo():
    return FakeAIChatRepository()


@pytest.fixture
def chat(repo):
    c = AIChat(
        uid="chat-1",
        user_uid="user-1",
        title="Test",
        model="",
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
    )
    repo.create_chat(c)
    return c


def test_create_chat(repo):
    chat = create_ai_chat(repository=repo, user_uid="user-1", title="Q&A")
    assert chat.uid
    assert chat.user_uid == "user-1"
    assert chat.title == "Q&A"


def test_list_chats_only_owner(repo):
    create_ai_chat(repository=repo, user_uid="user-1", title="A")
    create_ai_chat(repository=repo, user_uid="user-2", title="B")
    chats = list_ai_chats(repository=repo, user_uid="user-1")
    assert [c.title for c in chats] == ["A"]


def test_get_chat_ownership(repo, chat):
    with pytest.raises(AuthorizationFailed):
        get_ai_chat(repository=repo, chat_uid="chat-1", user_uid="user-9")


def test_get_chat_not_found(repo):
    with pytest.raises(NotFoundError):
        get_ai_chat(repository=repo, chat_uid="missing", user_uid="user-1")


def test_get_messages_ownership(repo, chat):
    with pytest.raises(AuthorizationFailed):
        get_ai_chat_messages(
            repository=repo, chat_uid="chat-1", user_uid="user-9", limit=50
        )


def test_send_message_streams_and_records_usage(repo, chat):
    gateway = FakeGateway()
    billing = FakeBilling()

    events = _collect(
        send_ai_message_stream(
            repository=repo,
            tokenizer=FakeTokenizer(),
            gateway=gateway,
            billing=billing,
            chat_uid="chat-1",
            user_uid="user-1",
            content="Hi there",
        )
    )

    assert gateway.streamed
    content = "".join(e["content"] for e in events if e["type"] == "chunk")
    assert content == "Hello world"

    messages = repo.list_messages("chat-1")
    roles = [m.role for m in messages]
    assert roles == ["user", "assistant"]
    assert messages[1].content == "Hello world"

    usages = repo.usages
    assert len(usages) == 1
    assert usages[0].user_uid == "user-1"
    assert usages[0].actual_input_tokens == 10
    assert usages[0].actual_output_tokens == 5
    # 10 вх. токенов некэшированных: 10*0.30/1000=0.003; 5 вых: 5*0.50/1000=0.0025 → 0.0055
    assert usages[0].actual_cost == "0.0055"

    usage_evt = [e for e in events if e["type"] == "usage"][0]
    assert usage_evt["cost"] == "0.0055"
    assert usage_evt["cached_tokens"] == 0
    # вход 10*0.30/1000=0.003; кэш 0; выход 5*0.50/1000=0.0025; инструменты 0
    assert usage_evt["cost_breakdown"] == {
        "input": "0.003",
        "cached": "0",
        "output": "0.0025",
        "tool": "0",
    }
    assert usage_evt["deducted"] is True
    assert billing.calls and billing.calls[0]["reference_id"] == usages[0].provider_request_id
    # 0.0055 ₽ → ceil → 1 копейка
    assert billing.calls[0]["amount"] == 1
    assert events[-1]["type"] == "done"


def test_send_message_foreign_chat_blocked(repo, chat):
    with pytest.raises(AuthorizationFailed):
        _collect(
            send_ai_message_stream(
                repository=repo,
                tokenizer=FakeTokenizer(),
                gateway=FakeGateway(),
                billing=FakeBilling(),
                chat_uid="chat-1",
                user_uid="user-9",
                content="x",
            )
        )


def test_send_message_records_cached_tokens_and_breakdown(repo, chat):
    gateway = FakeGateway(
        usage={
            "prompt_tokens": 2000,
            "prompt_cache_hit_tokens": 1200,
            "completion_tokens": 300,
            "total_tokens": 2300,
            "tool_tokens": 50,
        }
    )
    events = _collect(
        send_ai_message_stream(
            repository=repo,
            tokenizer=FakeTokenizer(),
            gateway=gateway,
            billing=FakeBilling(),
            chat_uid="chat-1",
            user_uid="user-1",
            content="Hi",
        )
    )

    usage = repo.usages[0]
    # 1200 кэш *0.075/1000=0.09; 800 некэш *0.30/1000=0.24; 300 вых *0.50/1000=0.15;
    # 50 инструментов *0.075/1000=0.00375 → 0.48375
    assert usage.actual_cached_tokens == 1200
    assert usage.actual_cost == "0.48375"

    usage_evt = [e for e in events if e["type"] == "usage"][0]
    assert usage_evt["cached_tokens"] == 1200
    assert usage_evt["cost_breakdown"] == {
        "input": "0.24",
        "cached": "0.09",
        "output": "0.15",
        "tool": "0.00375",
    }


def test_usage_summary_period(repo, chat):
    for _ in range(2):
        _collect(
            send_ai_message_stream(
                repository=repo,
                tokenizer=FakeTokenizer(),
                gateway=FakeGateway(),
                billing=FakeBilling(),
                chat_uid="chat-1",
                user_uid="user-1",
                content="Hi",
            )
        )

    summary = usage_summary(repository=repo, user_uid="user-1", period="current")
    assert summary["request_count"] == 2
    assert summary["input_tokens"] == 20
    assert summary["output_tokens"] == 10
    # 2 * 0.0055 = 0.011
    assert summary["cost"] == "0.011"


def _payload_for_messages(repo, chat_uid):
    from src.routers.ai_chats import _message_payload

    messages = repo.list_messages(chat_uid, limit=100)
    usages = repo.list_usage_for_chat(chat_uid, limit=100)
    usage_by_message = {u.message_uid: u for u in usages}
    return [_message_payload(m, usage_by_message, messages) for m in messages]


def test_messages_payload_distributes_usage_to_pair(repo, chat):
    gateway = FakeGateway(
        usage={
            "prompt_tokens": 2000,
            "prompt_cache_hit_tokens": 1200,
            "completion_tokens": 300,
            "total_tokens": 2300,
            "tool_tokens": 50,
        }
    )
    _collect(
        send_ai_message_stream(
            repository=repo,
            tokenizer=FakeTokenizer(),
            gateway=gateway,
            billing=FakeBilling(),
            chat_uid="chat-1",
            user_uid="user-1",
            content="Привет",
        )
    )

    payloads = _payload_for_messages(repo, "chat-1")
    assert len(payloads) == 2
    assert payloads[0]["role"] == "user"
    assert payloads[1]["role"] == "assistant"

    # user-сообщение: входная часть (input + кэш), стоимость входа
    user = payloads[0]
    assert user["tokens"] == 2000
    assert user["input_tokens"] == 2000
    assert user["cached_tokens"] == 1200
    assert user["tool_tokens"] == 0
    assert user["cache_used"] is True
    # 800 * 0.30/1000 + 1200 * 0.075/1000 = 0.24 + 0.09 = 0.33
    assert user["cost"] == "0.33"
    assert user["cost_breakdown"] == {
        "input": "0.24",
        "cached": "0.09",
        "output": "0",
        "tool": "0",
    }

    # assistant-сообщение: выходная часть (output + инструменты)
    assistant = payloads[1]
    assert assistant["tokens"] == 300
    assert assistant["input_tokens"] == 0
    assert assistant["cached_tokens"] == 0
    assert assistant["tool_tokens"] == 50
    assert assistant["cache_used"] is False
    # 300 * 0.50/1000 + 50 * 0.075/1000 = 0.15 + 0.00375 = 0.15375
    assert assistant["cost"] == "0.15375"
    assert assistant["cost_breakdown"] == {
        "input": "0",
        "cached": "0",
        "output": "0.15",
        "tool": "0.00375",
    }
    # суммарная стоимость пары совпадает с фактической
    assert str((float(user["cost"]) + float(assistant["cost"]))) == "0.48375"


def test_messages_payload_without_usage(repo, chat):
    from domain.models.ai_chat import AIMessage

    repo.add_message(
        AIMessage(
            uid="u1",
            chat_uid="chat-1",
            role="user",
            content="Вопрос без ответа",
            order=1,
            created_at=datetime(2026, 1, 1),
        )
    )
    payloads = _payload_for_messages(repo, "chat-1")
    assert len(payloads) == 1
    assert payloads[0]["tokens"] is None
    assert payloads[0]["cost"] is None
    assert payloads[0]["cache_used"] is False

"""
Layer: Domain (Entities)
Package: domain.models.ai_chat
Responsibility: Чистое представление AI-чата, сообщения и usage.

Принадлежит слою Domain — только бизнес-атрибуты, без Neo4j/FastAPI/gRPC.
Деньги представлены строковым представлением Decimal (точность 8 знаков),
копейки вычисляются на этапе списания через billing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class AIChat:
    """Персистентный чат пользователя с AI-ассистентом."""

    uid: str
    user_uid: str
    title: str = ""
    model: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class AIMessage:
    """Сообщение в AI-чате (user / assistant / system)."""

    uid: str
    chat_uid: str
    role: str
    content: str
    order: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    usage: Optional["AIUsage"] = None


@dataclass
class AIUsage:
    """Учёт токенов и стоимости одного запроса.

    Деньги — строки с точным Decimal-представлением (например "0.28625").
    ``provider_request_id`` — id ответа провайдера, используется для
    идемпотентного списания через billing.
    """

    uid: str
    message_uid: str
    chat_uid: str
    user_uid: str
    model: str
    provider_request_id: str
    estimated_input_tokens: int
    estimated_output_tokens: int
    estimated_cached_tokens: Optional[int]
    estimated_cost: str
    actual_input_tokens: int
    actual_cached_tokens: int
    actual_output_tokens: int
    actual_tool_tokens: int
    actual_cost: str
    currency: str = "RUB"
    created_at: datetime = field(default_factory=datetime.utcnow)

"""
Layer: Application (Use Cases) — Ports
Package: application.ports.ai_chat_repository
Responsibility: Protocol-интерфейсы для AI-чатов (driven ports).

Принадлежит слою Application. Протоколы описывают контракт, который
реализуют адаптеры (adapters/repositories/) с помощью neomodel.
Structural subtyping (typing.Protocol) — без явного наследования.
"""
from __future__ import annotations

from typing import List, Optional, Protocol

from domain.models.ai_chat import AIChat, AIMessage, AIUsage


class AIChatRepositoryProtocol(Protocol):
    """Репозиторий AI-чатов и сообщений."""

    def get_chat(self, chat_uid: str) -> Optional[AIChat]: ...

    def list_chats(self, user_uid: str, limit: int = 50) -> List[AIChat]: ...

    def create_chat(self, chat: AIChat) -> AIChat: ...

    def touch_chat(self, chat_uid: str) -> None: ...

    def list_messages(self, chat_uid: str, limit: int = 100) -> List[AIMessage]: ...

    def add_message(self, message: AIMessage) -> AIMessage: ...

    def save_usage(self, usage: AIUsage) -> AIUsage: ...

    def get_usage_by_provider_id(self, provider_request_id: str) -> Optional[AIUsage]: ...

    def list_usage_for_user(
        self,
        user_uid: str,
        since: Optional[float] = None,
        until: Optional[float] = None,
        limit: int = 100,
    ) -> List[AIUsage]: ...

    def list_usage_for_chat(self, chat_uid: str, limit: int = 100) -> List[AIUsage]: ...

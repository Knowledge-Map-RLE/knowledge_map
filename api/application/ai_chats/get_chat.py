"""
Layer: Application (Use Cases)
Package: application.ai_chats.get_chat
Responsibility: Получение AI-чата с проверкой владельца и истории сообщений.

Принадлежит слою Application: оркестрирует репозиторий, не знает о фреймворках.
"""
from __future__ import annotations

from typing import List, Optional

from domain.exceptions import AuthorizationFailed, NotFoundError
from domain.models.ai_chat import AIChat, AIMessage


def get_ai_chat(
    *,
    repository,
    chat_uid: str,
    user_uid: str,
) -> AIChat:
    chat = repository.get_chat(chat_uid)
    if chat is None:
        raise NotFoundError("AIChat", chat_uid)
    if chat.user_uid != user_uid:
        raise AuthorizationFailed("Чат принадлежит другому пользователю")
    return chat


def get_ai_chat_messages(
    *,
    repository,
    chat_uid: str,
    user_uid: str,
    limit: int = 100,
) -> List[AIMessage]:
    get_ai_chat(repository=repository, chat_uid=chat_uid, user_uid=user_uid)
    return repository.list_messages(chat_uid, limit=limit)

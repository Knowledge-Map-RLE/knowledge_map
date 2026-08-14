"""
Layer: Application (Use Cases)
Package: application.ai_chats.list_chats
Responsibility: Список AI-чатов пользователя.

Принадлежит слою Application: оркестрирует репозиторий, не знает о фреймворках.
"""
from __future__ import annotations

from typing import List

from domain.models.ai_chat import AIChat


def list_ai_chats(
    *,
    repository,
    user_uid: str,
    limit: int = 50,
) -> List[AIChat]:
    return repository.list_chats(user_uid, limit=limit)

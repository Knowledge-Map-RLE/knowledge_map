"""
Layer: Application (Use Cases)
Package: application.ai_chats.create_chat
Responsibility: Создание персистентного AI-чата.

Принадлежит слою Application: оркестрирует репозиторий, не знает о фреймворках.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from domain.models.ai_chat import AIChat


def create_ai_chat(
    *,
    repository,
    user_uid: str,
    title: str = "",
    model: str = "",
) -> AIChat:
    now = datetime.utcnow()
    chat = AIChat(
        uid=str(uuid.uuid4()),
        user_uid=user_uid,
        title=title,
        model=model,
        created_at=now,
        updated_at=now,
    )
    return repository.create_chat(chat)

"""
Layer: Domain (Entities)
Package: domain.models.feedback
 Responsibility: Dataclass-ы системы обратной связи (баг-репорты, пожелания).

Принадлежит слою Domain — чистые dataclass-ы без зависимостей от инфраструктуры.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any


class FeedbackStatus(str, enum.Enum):
    """Статус обращения пользователя."""
    NEW = "new"
    IN_DEVELOPMENT = "in_development"
    RESOLVED = "resolved"
    REJECTED = "rejected"


STATUS_COLORS: dict[FeedbackStatus, str] = {
    FeedbackStatus.NEW: "#3B82F6",
    FeedbackStatus.IN_DEVELOPMENT: "#F97316",
    FeedbackStatus.RESOLVED: "#22C55E",
    FeedbackStatus.REJECTED: "#1F2937",
}

STATUS_LABELS: dict[FeedbackStatus, str] = {
    FeedbackStatus.NEW: "Новое",
    FeedbackStatus.IN_DEVELOPMENT: "В разработке",
    FeedbackStatus.RESOLVED: "Решено",
    FeedbackStatus.REJECTED: "Отклонено",
}


@dataclass(frozen=True)
class BrowserInfo:
    """Метаданные браузера и среды пользователя."""
    user_agent: str = ""
    language: str = ""
    platform: str = ""
    screen_width: int = 0
    screen_height: int = 0
    window_width: int = 0
    window_height: int = 0
    timezone: str = ""
    cookie_enabled: bool = False
    device_memory: int = 0
    hardware_concurrency: int = 0
    connection_type: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_agent": self.user_agent,
            "language": self.language,
            "platform": self.platform,
            "screen_width": self.screen_width,
            "screen_height": self.screen_height,
            "window_width": self.window_width,
            "window_height": self.window_height,
            "timezone": self.timezone,
            "cookie_enabled": self.cookie_enabled,
            "device_memory": self.device_memory,
            "hardware_concurrency": self.hardware_concurrency,
            "connection_type": self.connection_type,
        }


@dataclass(frozen=True)
class FeedbackTicket:
    """Обратная связь (баг-репорт или пожелание)."""
    uid: str
    user_uid: str
    status: FeedbackStatus = FeedbackStatus.NEW
    browser_info: dict[str, Any] = field(default_factory=dict)
    app_version: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0


@dataclass(frozen=True)
class FeedbackMessage:
    """Сообщение в чате обращения."""
    uid: str
    ticket_uid: str
    sender_uid: str
    sender_type: str  # "user" | "admin"
    text: str = ""
    image_s3_keys: list[str] = field(default_factory=list)
    created_at: float = 0.0


@dataclass(frozen=True)
class FeedbackDraft:
    """Черновик сообщения (привязан к пользователю, один на аккаунт)."""
    user_uid: str
    text: str = ""
    updated_at: float = 0.0

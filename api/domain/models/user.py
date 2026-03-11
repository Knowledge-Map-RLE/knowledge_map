"""
Layer: Domain (Entities)
Package: domain.models.user
Responsibility: Чистое представление пользователя.

Allowed imports: только стандартная библиотека Python
Forbidden imports: neomodel, pydantic, fastapi
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Any


@dataclass
class User:
    """Пользователь системы."""
    uid: str
    login: str
    nickname: str
    data: Optional[Any] = None

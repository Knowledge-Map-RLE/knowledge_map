"""Утилиты работы с тегами DSL: B<число> (ссылка на строку) и S<число> (source unit).

Тег ``B5`` — ссылка на структурную строку; ``S12`` — ссылка на предложение
(source unit). Используются парсером DSL и выявлением закономерностей между
строками.
"""
from __future__ import annotations

import re
from typing import Iterable, List, Optional

_REF_RE = re.compile(r"\bB(\d{1,6})\b")
_UNIT_RE = re.compile(r"\bS(\d{1,6})\b")


def iter_tags(value: str) -> List[str]:
    """Извлекает все теги ``B<число>`` из значения (например ``"groupRefs=[B5,B6]"`` без ключа)."""
    return [f"B{m}" for m in _REF_RE.findall(str(value))]


def iter_units(value: str) -> List[str]:
    """Извлекает все теги ``S<число>`` из значения."""
    return [f"S{m}" for m in _UNIT_RE.findall(str(value))]


def parse_tags_list(value: str) -> List[str]:
    """Разбирает ``[B5,B6]`` или ``B5,B6`` или одиночный ``B6`` в список тегов.

    Возвращает канонические теги ``B<число>`` (с префиксом, без дублей).
    """
    return list(dict.fromkeys(iter_tags(value)))


def strip_brackets(value: str) -> str:
    """Убирает обрамляющие квадратные скобки в списке ``[a,b]``."""
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        return value[1:-1]
    return value


def split_list_value(value: str) -> Optional[List[str]]:
    """Разбивает значение-список ``[a,b]`` на элементы; для одиночных значений — None."""
    stripped = value.strip()
    if not (stripped.startswith("[") and stripped.endswith("]")):
        return None
    inner = stripped[1:-1]
    if not inner.strip():
        return []
    return [p.strip() for p in inner.split(",") if p.strip()]


def sanitize_value(value: str) -> str:
    """Очищает значение поля: убирает восстанавливаемые пробелы/кавычки, не трогает теги."""
    return value.strip().strip("\"'`").strip()
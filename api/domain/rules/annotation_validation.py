"""
Layer: Domain (Entities) — Business Rules
Package: domain.rules.annotation_validation
Responsibility: Валидация позиционных данных аннотации (offsets).

Allowed imports: только стандартная библиотека Python
Forbidden imports: neomodel, fastapi, pydantic
"""
from __future__ import annotations

from domain.exceptions import DomainValidationError


def validate_offsets(start_offset: int, end_offset: int) -> None:
    """
    Проверяет корректность позиции аннотации в тексте.

    Raises:
        DomainValidationError: если offsets некорректны.
    """
    if start_offset < 0:
        raise DomainValidationError("start_offset", "не может быть отрицательным")
    if end_offset <= start_offset:
        raise DomainValidationError(
            "end_offset",
            f"должен быть больше start_offset ({start_offset}), получено {end_offset}",
        )

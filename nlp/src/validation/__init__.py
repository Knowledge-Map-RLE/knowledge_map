"""Модуль валидации канонического Markdown формата."""

from .types import (
    ValidationResult,
    ValidationError,
    ErrorType,
    ErrorSeverity,
    Citation,
    Reference,
)
from .markdown_validator import validate_markdown

__all__ = [
    'validate_markdown',
    'ValidationResult',
    'ValidationError',
    'ErrorType',
    'ErrorSeverity',
    'Citation',
    'Reference',
]

"""
Типы данных для валидации канонического Markdown.

Следует функциональной парадигме NLP сервиса с использованием
неизменяемых dataclass'ов.
"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum


class ErrorSeverity(Enum):
    """Уровни серьёзности ошибок валидации."""
    ERROR = "error"       # Критическая ошибка, должна быть исправлена
    WARNING = "warning"   # Предупреждение, рекомендуется исправить
    INFO = "info"         # Информационное сообщение


class ErrorType(Enum):
    """Типы ошибок валидации."""
    # Ошибки frontmatter
    MISSING_FRONTMATTER = "missing_frontmatter"
    INVALID_YAML = "invalid_yaml"
    MALFORMED_FRONTMATTER = "malformed_frontmatter"

    # Ошибки заголовков
    MULTIPLE_H1 = "multiple_h1"
    MISSING_H1 = "missing_h1"

    # Ошибки таблиц
    MARKDOWN_TABLE_FOUND = "markdown_table_found"

    # Ошибки изображений
    MARKDOWN_IMAGE_FOUND = "markdown_image_found"

    # Ошибки ссылок и ссылок
    MISSING_REFERENCES_SECTION = "missing_references_section"
    CITATION_WITHOUT_REFERENCE = "citation_without_reference"
    ORPHANED_REFERENCE = "orphaned_reference"
    DUPLICATE_REFERENCE_NUMBER = "duplicate_reference_number"
    MALFORMED_REFERENCE = "malformed_reference"
    MALFORMED_CITATION = "malformed_citation"


@dataclass(frozen=True)
class ValidationError:
    """
    Одна ошибка валидации с информацией о местоположении.

    Неизменяемый dataclass следуя функциональной парадигме.
    """
    error_type: ErrorType
    message: str
    severity: ErrorSeverity

    # Информация о местоположении (минимум одно поле должно быть заполнено)
    line: Optional[int] = None          # Номер строки (1-индексированный)
    column: Optional[int] = None        # Номер колонки (1-индексированный)
    start_offset: Optional[int] = None  # Смещение символа в тексте (0-индексированный)
    end_offset: Optional[int] = None    # Конец смещения символа

    # Контекст ошибки
    context: Optional[str] = None       # Текст вокруг ошибки
    suggestion: Optional[str] = None    # Рекомендация как исправить

    # Дополнительные метаданные
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationResult:
    """
    Полный результат валидации документа Markdown.

    Изменяемый dataclass для накопления ошибок во время валидации.
    """
    is_valid: bool
    errors: List[ValidationError] = field(default_factory=list)
    warnings: List[ValidationError] = field(default_factory=list)

    # Метаданные о валидации
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Статистика
    total_errors: int = 0
    total_warnings: int = 0

    def add_error(self, error: ValidationError) -> None:
        """Добавить ошибку и обновить счётчик."""
        if error.severity == ErrorSeverity.ERROR:
            self.errors.append(error)
            self.total_errors += 1
            self.is_valid = False
        elif error.severity == ErrorSeverity.WARNING:
            self.warnings.append(error)
            self.total_warnings += 1

    def merge(self, other: 'ValidationResult') -> None:
        """Объединить результат другой валидации с этим."""
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)
        self.total_errors += other.total_errors
        self.total_warnings += other.total_warnings
        if not other.is_valid:
            self.is_valid = False
        self.metadata.update(other.metadata)


@dataclass(frozen=True)
class Citation:
    """Цитата найденная в документе [N]."""
    number: int                # Номер цитаты
    start_offset: int         # Начало в тексте
    end_offset: int           # Конец в тексте
    line: int                 # Номер строки
    column: int               # Номер колонки
    context: str              # Окружающий текст


@dataclass(frozen=True)
class Reference:
    """Запись ссылки в разделе References."""
    number: int               # Номер ссылки
    text: str                 # Полный библиографический текст
    start_offset: int         # Начало в тексте
    end_offset: int           # Конец в тексте
    line: int                 # Номер строки

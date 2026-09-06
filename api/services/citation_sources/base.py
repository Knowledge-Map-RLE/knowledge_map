"""
Layer: Domain — Value Objects & Port
Package: services.citation_sources.base
Responsibility: Абстрактный интерфейс источника цитат и dataclass для рёбер графа.
"""
from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator, Callable, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CitationEdge:
    """Одно ребро цитатного графа: citing_doi --[cites]--> cited_doi.

    Поля _citing/_cited — метаданные работ; заполняются тем источником, который
    их знает (например, OpenAlex даёт topics). Тематика используется картой
    science_articles для фильтрации по научным областям.
    """

    citing_doi: str
    cited_doi: str
    source: str
    title_citing: Optional[str] = None
    title_cited: Optional[str] = None
    primary_field_citing: Optional[str] = None
    fields_citing: Optional[tuple[str, ...]] = None
    primary_field_cited: Optional[str] = None
    fields_cited: Optional[tuple[str, ...]] = None


@dataclass(frozen=True, slots=True)
class BulkLoadOptions:
    """Ограничения массовой загрузки из дампа.

    max_files: обработать только первые N файлов/архивных members.
    max_records: обработать только первые N записей (строк дампа).
    Если задано хотя бы одно ограничение — чекпоинт не перезаписывается
    (повторный запуск с тем же лимитом даёт тот же результат, а полная
    загрузка продолжит с последнего «честного» чекпоинта).
    """

    max_files: Optional[int] = None
    max_records: Optional[int] = None

    def is_limited(self) -> bool:
        return self.max_files is not None or self.max_records is not None

    def __post_init__(self) -> None:
        if self.max_files is not None and self.max_files <= 0:
            raise ValueError("max_files must be positive")
        if self.max_records is not None and self.max_records <= 0:
            raise ValueError("max_records must be positive")


@dataclass(slots=True)
class TestEstimate:
    """Результат тестового прогона: время на N записей + экстраполяция."""

    source_name: str
    sample_size: int
    elapsed_seconds: float
    edges_found: int
    estimated_total_edges: Optional[int] = None
    estimated_time_seconds: Optional[float] = None
    errors: list[str] = field(default_factory=list)
    success: bool = True


class CitationSource(ABC):
    """Интерфейс для всех источников цитат."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Уникальный ключ источника (opencitations / openalex / crossref / datacite)."""
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Человекочитаемое название."""
        ...

    @abstractmethod
    async def get_one(self, doi: str) -> list[CitationEdge]:
        """Получить все цитаты для DOI через API (citing + cited)."""
        ...

    @abstractmethod
    async def get_all(
        self,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        options: Optional[BulkLoadOptions] = None,
        cancel_callback: Optional[Callable[[], bool]] = None,
    ) -> AsyncIterator[CitationEdge]:
        """Массовая загрузка из дампа. yield'ит edges порциями.

        Args:
            progress_callback: Функция (processed_bytes, total_bytes, current_file) -> None
            options: Ограничения частичной загрузки (первые N файлов/записей).
            cancel_callback: Callable, возвращающий True, если загрузку следует
                остановить (кооперативная отмена между порциями).
        """
        ...

    @abstractmethod
    async def test_estimate(self, sample_size: int = 10) -> TestEstimate:
        """Тест: скачать sample_size записей через API и оценить время полной загрузки."""
        ...

    async def _test_get_one_timing(self, doi: str) -> tuple[float, list[CitationEdge]]:
        """Вспомогательный: замер времени одного get_one запроса."""
        t0 = time.monotonic()
        edges = await self.get_one(doi)
        elapsed = time.monotonic() - t0
        return elapsed, edges

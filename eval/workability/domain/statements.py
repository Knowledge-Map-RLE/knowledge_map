"""
Domain — модели утверждений и статей.

Единица прогноза и оценки — каноническое утверждение (canonical statement),
идентифицируемое по ключу ``norm_key`` (нормализованный хеш субъект|предикат|объект,
уже вычисляется в пайплайне как sha256[:16]).

Статья — это контейнер, владеющий множеством утверждений. Сравнение между
предсказанием и реальностью всегда ведётся на уровне утверждений, а не текстов.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Set


@dataclass(frozen=True)
class CanonicalStatement:
    """Каноническое утверждение — единица прогноза и оценки.

    ``norm_key`` — нормализованный идентификатор утверждения. Это ОБЯЗАТЕЛЬНОЕ
    поле (якорь сравнения). Остальные поля — диагностические, для отчёта.
    """
    norm_key: str
    verb: str = ""
    subject: str = ""
    object: str = ""
    label_text: str = ""
    doc_id: Optional[str] = None


@dataclass
class Article:
    """Статья — контейнер утверждений.

    ``doc_id`` соответствует ``Action.doc_id`` и ``Document.uid`` в Neo4j.
    ``statements`` — множество канонических утверждений, извлечённых из статьи.
    """
    doc_id: str
    statements: Set[str] = field(default_factory=set)

    def add_statement(self, norm_key: str) -> None:
        self.statements.add(norm_key)

    def add_statements(self, norm_keys: Set[str]) -> None:
        self.statements.update(norm_keys)

    def __contains__(self, norm_key: str) -> bool:
        return norm_key in self.statements


@dataclass
class TemporalSnapshot:
    """Исторический граф знаний на момент времени T.

    Содержит ТОЛЬКО данные статей с publication_date <= T (без утечки будущего).

    Attributes:
        year:       контрольная точка T (год).
        articles:   doc_id -> Article (статьи <= T).
        article_years: doc_id -> год публикации.
        bibliographic_edges: set[(src_doc, tgt_doc)] рёбра BIBLIOGRAPHIC_LINK
            между статьями снапшота. Направление source(cited) -> target(citing).
    """
    year: int
    articles: Dict[str, Article] = field(default_factory=dict)
    article_years: Dict[str, int] = field(default_factory=dict)
    bibliographic_edges: Set[tuple[str, str]] = field(default_factory=set)

    # --- Удобные сводки ------------------------------------------------ #

    @property
    def article_ids(self) -> Set[str]:
        return set(self.articles.keys())

    @property
    def all_statement_keys(self) -> Set[str]:
        """Все norm_key утверждений в снапшоте."""
        result: Set[str] = set()
        for art in self.articles.values():
            result |= art.statements
        return result

    def docs_for_statement(self, norm_key: str) -> Set[str]:
        """Документы снапшота, содержащие заданное утверждение."""
        return {
            doc_id
            for doc_id, art in self.articles.items()
            if norm_key in art.statements
        }

    def articles_after(self, min_year: int) -> Dict[str, Article]:
        """Возвращает статьи с publication_date > min_year (для будущих данных)."""
        return {
            doc_id: art
            for doc_id, art in self.articles.items()
            if self.article_years.get(doc_id, min_year + 1) > min_year
        }

    def count_statements(self) -> int:
        return len(self.all_statement_keys)

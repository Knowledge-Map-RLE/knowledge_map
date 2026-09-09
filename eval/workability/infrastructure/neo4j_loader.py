"""
Infrastructure — загрузка данных из Neo4j для backtesting.

Отвечает за:
  - извлечение документов/статей с publication_date,
  - извлечение Action (norm_key, verb, subject, object_, label_text, doc_id),
  - извлечение рёбер BIBLIOGRAPHIC_LINK между статьями (для KPI-2),
  - сборку TemporalSnapshot для заданных контрольных точек T.

Использует neomodel (как metrics_loop.py / quality_check.py) и прямой
db.cypher_query. Масштабируемость: запросы постраничные (SKIP/LIMIT) с
курсорной загрузкой, чтобы не выгружать миллионы строк за раз.

Запуск — из окружения api/ (poetry run python ..\\eval\\workability\\cli.py).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional, Set

from neomodel import config as neomodel_config, db

from ..domain.statements import Article, CanonicalStatement, TemporalSnapshot

logger = logging.getLogger(__name__)

_PAGE = 5000


class Neo4jLoader:
    """Загрузчик данных Карты Знаний из Neo4j для построения снапшотов."""

    def __init__(self, url: Optional[str] = None) -> None:
        if url:
            neomodel_config.DATABASE_URL = url

    # ─── Публикационные даты документов ──────────────────────────────── #

    def load_article_years(
        self, limit: Optional[int] = None, doc_ids: Optional[Set[str]] = None
    ) -> Dict[str, int]:
        """doc_id -> год публикации для документов с publication_date.

        Использует маркерную пагинацию по d.uid (RANGE-индекс) — SKIP/LIMIT
        на 9.7M узлах пересортировывает выборку на каждой странице (крайне
        медленно). limit — ограничить число документов (для смоук-тестов);
        doc_ids — вернуть годы только для указанных документов.
        """
        years: Dict[str, int] = {}
        if doc_ids is not None and not doc_ids:
            return years
        last = ""
        while limit is None or len(years) < limit:
            params: Dict[str, Any] = {"last": last, "page": _PAGE}
            where = "WHERE d.publication_date IS NOT NULL AND d.uid > $last"
            if doc_ids is not None:
                where += " AND d.uid IN $doc_ids"
                params["doc_ids"] = list(doc_ids)
            if limit is not None:
                params["page"] = min(_PAGE, limit - len(years))
            r, _ = db.cypher_query(
                f"""
                MATCH (d:Document)
                {where}
                WITH d ORDER BY d.uid LIMIT $page
                RETURN d.uid AS uid, d.publication_date AS pub
                """,
                params,
            )
            if not r:
                break
            for uid, pub in r:
                year = _extract_year(pub)
                if year:
                    years[uid] = year
            last = str(r[-1][0])
            if len(r) < params["page"]:
                break
        return years

    # ─── Утверждения (Action) ────────────────────────────────────────── #

    def load_statement_doc_ids(self, limit: Optional[int] = None) -> Set[str]:
        """Возвращает doc_id всех статей, у которых есть утверждения (Action).

        Используется для смоук-тестов: ограниченная выборка статей должна
        содержать утверждения, иначе backtest не имеет ни одного case.
        """
        doc_ids: Set[str] = set()
        tail = "RETURN d" if limit is None else "ORDER BY d LIMIT $limit RETURN d"
        r, _ = db.cypher_query(
            "MATCH (a:Action) WHERE a.doc_id IS NOT NULL "
            f"WITH DISTINCT a.doc_id AS d {tail}",
            {"limit": limit} if limit is not None else {},
        )
        for (doc_id,) in r:
            doc_ids.add(str(doc_id))
        return doc_ids

    def load_statements(
        self,
        doc_ids: Optional[Set[str]] = None,
        progress_limit: Optional[int] = None,
    ) -> List[CanonicalStatement]:
        """Загружает канонические утверждения из Action-узлов.

        Args:
            doc_ids: если задано — только эти статьи (фильтр для сниппетов/тестов).
                Пустое множество допустимо — вернёт пустой список.
            progress_limit: если задано — ограничение числа обработанных статей
                (LIMIT для быстрого прогона).
        """
        statements: List[CanonicalStatement] = []
        if doc_ids is not None and not doc_ids:
            return statements

        offset = 0
        while True:
            params: Dict[str, Any] = {"offset": offset, "page": _PAGE}
            where = ""
            if doc_ids is not None:
                ids = list(doc_ids)
                where = "WHERE a.doc_id IN $doc_ids "
                params["doc_ids"] = ids
            elif progress_limit is not None:
                # Ограничить по числу готовых статей через WorkerArticleProgress.
                where = (
                    "WHERE a.doc_id IN "
                    "(MATCH (p:WorkerArticleProgress {state:'done'}) "
                    " WITH p.doc_id LIMIT $limit ) "
                )
                params["limit"] = progress_limit

            r, _ = db.cypher_query(
                f"""
                MATCH (a:Action)
                {where}
                WITH a ORDER BY a.uid SKIP $offset LIMIT $page
                RETURN a.norm_key AS nk, a.verb AS verb, a.subject AS subj,
                       a.object AS obj, a.label_text AS label, a.doc_id AS doc_id
                """,
                params,
            )
            if not r:
                break
            for nk, verb, subj, obj, label, doc_id in r:
                if not nk:
                    continue
                statements.append(
                    CanonicalStatement(
                        norm_key=str(nk),
                        verb=str(verb or ""),
                        subject=str(subj or ""),
                        object=str(obj or ""),
                        label_text=str(label or ""),
                        doc_id=str(doc_id) if doc_id else None,
                    )
                )
            if len(r) < _PAGE:
                break
            offset += _PAGE
        return statements

    # ─── BIBLIOGRAPHIC_LINK между статьями ───────────────────────────── #

    def load_bibliographic_edges(
        self,
        doc_ids: Optional[Set[str]] = None,
    ) -> Set[tuple[str, str]]:
        """Загружает пары (src_doc, tgt_doc) рёбер BIBLIOGRAPHIC_LINK.

        Направление: source (cited, старая статья) -> target (citing, новая).
        """
        edges: Set[tuple[str, str]] = set()
        if doc_ids is not None and not doc_ids:
            return edges
        offset = 0
        while True:
            params: Dict[str, Any] = {"offset": offset, "page": _PAGE}
            where = ""
            if doc_ids is not None:
                ids = list(doc_ids)
                where = "WHERE src.uid IN $doc_ids AND tgt.uid IN $doc_ids "
                params["doc_ids"] = ids

            r, _ = db.cypher_query(
                f"""
                MATCH (src:Document)-[r:BIBLIOGRAPHIC_LINK]->(tgt:Document)
                {where}
                WITH src, tgt ORDER BY src.uid, tgt.uid SKIP $offset LIMIT $page
                RETURN src.uid AS sdoc, tgt.uid AS tdoc
                """,
                params,
            )
            if not r:
                break
            for sdoc, tdoc in r:
                if sdoc and tdoc and sdoc != tdoc:
                    edges.add((str(sdoc), str(tdoc)))
            if len(r) < _PAGE:
                break
            offset += _PAGE
        return edges

    # ─── Сборка снапшота ─────────────────────────────────────────────── #

    def build_snapshot(
        self,
        year: int,
        article_years: Dict[str, int],
        statements: List[CanonicalStatement],
        edges: Set[tuple[str, str]],
    ) -> TemporalSnapshot:
        """Собирает TemporalSnapshot для контрольной точки year.

        Учитывает только статьи с publication_year <= year (без утечки будущего)
        и рёбра цитирования между такими статьями.
        """
        # Статьи <= T
        doc_ids_le = {d for d, y in article_years.items() if y <= year}
        articles: Dict[str, Article] = {}
        art_years_snap: Dict[str, int] = {}

        for d in doc_ids_le:
            articles[d] = Article(doc_id=d)
            art_years_snap[d] = article_years[d]

        # Утверждения, принадлежащие этим статьям
        for st in statements:
            if st.doc_id is None or st.doc_id not in articles:
                continue
            articles[st.doc_id].add_statement(st.norm_key)

        # Рёбра цитирования между статьями снапшота
        snap_edges: Set[tuple[str, str]] = set()
        for src, tgt in edges:
            if src in articles and tgt in articles:
                snap_edges.add((src, tgt))

        return TemporalSnapshot(
            year=year,
            articles=articles,
            article_years=art_years_snap,
            bibliographic_edges=snap_edges,
        )


def _extract_year(pub_date: Any) -> Optional[int]:
    """Извлекает год из разнородных форматов publication_date.

    Neo4j DateTime -> int(grant.year), либо строка 'YYYY', либо datetime.date.
    """
    if pub_date is None:
        return None
    # Neo4j datetime / Python datetime / date
    if hasattr(pub_date, "year"):
        return int(pub_date.year)
    # Строка
    if isinstance(pub_date, str):
        s = pub_date.strip()
        if not s:
            return None
        # ищем первое 4-значное число года
        import re

        m = re.search(r"(?<!\d)(\d{4})(?!\d)", s)
        if m:
            year = int(m.group(1))
            if 1900 <= year <= 2100:
                return year
        return None
    # Число (epoch timestamp)
    if isinstance(pub_date, (int, float)):
        from datetime import datetime, timezone

        try:
            return datetime.fromtimestamp(pub_date, tz=timezone.utc).year
        except (ValueError, OSError, OverflowError):
            return None
    return None

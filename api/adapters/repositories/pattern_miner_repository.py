"""
Layer: Interface Adapters — Repository (Persistence)
Package: adapters.repositories.pattern_miner_repository
Responsibility: чтение утверждений (KnowledgeStatement) из Neo4j по корпусу
документов для алгоритма выявления паттернов.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

from neomodel import db

from application.patterns.statement_graph import statements_to_graph

logger = logging.getLogger(__name__)

# Рёбра-отношения, не несущие структуры (то же, что исключает graph editor)
_NOISE = {"is_a", "contains", "related_to"}


def _direction_of(predicate: str) -> str:
    """Свёртка предиката к направлению up|down|other (для сверки конфликтов)."""
    p = str(predicate or "").strip().lower()
    up = {"increase", "increases", "upregulate", "upregulates", "activate", "activates",
          "promote", "promotes", "stimulate", "stimulates", "raise", "raises"}
    down = {"decrease", "decreases", "downregulate", "downregulates", "reduce", "reduces",
            "suppress", "suppresses", "inhibit", "inhibits"}
    for t in up:
        if t in p:
            return "up"
    for t in down:
        if t in p:
            return "down"
    return "other"


def _flip(direction: str) -> str:
    return "down" if direction == "up" else ("up" if direction == "down" else "other")


def _find_conflict(
    by_pair: Dict[Tuple[str, str], List[str]],
    subj_key: str,
    obj_key: str,
    direction: str,
) -> Optional[str]:
    """Возвращает противоположное направление, если зафиксирован конфликт."""
    if direction not in {"up", "down"}:
        return None
    opp = _flip(direction)
    dirs = by_pair.get((subj_key, obj_key), [])
    if opp in dirs:
        return opp
    return None




class PatternMinerRepository:
    """Репозиторий загрузки утверждений для pattern-miner."""

    def load_corpus(
        self,
        doc_ids: Optional[Sequence[str]] = None,
        doc_limit: int = 200,
        statements_per_doc_cap: Optional[int] = None,
        noise_filter: bool = True,
    ) -> List[Dict[str, Any]]:
        """Возвращает утверждения корпуса, сгруппированные по документам.

        Args:
            doc_ids: ограничение корпуса по документам.
            doc_limit: максимум документов.
            statements_per_doc_cap: максимум утверждений на документ
                (детерминированный шаг-сэмплинг по sort_order) — защита от
                экспоненциального роста перебора в gSpan на больших статьях.
            noise_filter: если False — не отсекать шумовые предикаты
                (is_a/contains/related_to); нужно для генерации категориальных
                выводов (силлогизмы).

        Returns:
            [{"doc_id", "statements": [dict], "count"}]
        """
        params: Dict[str, Any] = {}
        where_noise = ""
        if noise_filter:
            params["noise"] = list(_NOISE)
            where_noise = "AND NOT s.predicate IN $noise "
        if doc_ids:
            params["doc_ids"] = list(doc_ids)
            rows, _ = db.cypher_query(
                "MATCH (d:Document)-[:HAS_STATEMENT]->(s:KnowledgeStatement) "
                "WHERE s.predicate IS NOT NULL AND s.predicate <> '' "
                + where_noise +
                "AND d.uid IN $doc_ids "
                "RETURN d.uid AS doc_id, s.uid AS uid, s.subject_text AS subject_text, "
                "s.predicate AS predicate, s.object_text AS object_text, "
                "s.subject_type AS subject_type, s.object_type AS object_type, "
                "s.type AS type, s.confidence AS confidence "
                "ORDER BY doc_id, s.sort_order",
                params,
            )
        else:
            # Весь корпус: сначала выбираем ограниченный набор документов,
            # затем их утверждения (избегаем огромного расширения по всем
            # миллионам документов БД).
            rows, _ = db.cypher_query(
                "MATCH (d:Document) "
                "WHERE EXISTS { (d)-[:HAS_STATEMENT]->(:KnowledgeStatement) } "
                "WITH d LIMIT $doc_limit "
                "MATCH (d)-[:HAS_STATEMENT]->(s:KnowledgeStatement) "
                "WHERE s.predicate IS NOT NULL AND s.predicate <> '' "
                + where_noise +
                "RETURN d.uid AS doc_id, s.uid AS uid, s.subject_text AS subject_text, "
                "s.predicate AS predicate, s.object_text AS object_text, "
                "s.subject_type AS subject_type, s.object_type AS object_type, "
                "s.type AS type, s.confidence AS confidence "
                "ORDER BY doc_id, s.sort_order",
                {**params, "doc_limit": max(1, int(doc_limit))},
            )

        by_doc: Dict[str, List[Dict[str, Any]]] = {}
        for r in rows:
            doc_id = r[0]
            stmt = {
                "uid": r[1],
                "subject_text": r[2],
                "predicate": r[3],
                "object_text": r[4],
                "subject_type": r[5],
                "object_type": r[6],
                "type": r[7],
                "confidence": r[8],
            }
            by_doc.setdefault(doc_id, []).append(stmt)

        out = []
        for doc_id, statements in sorted(by_doc.items()):
            if statements_per_doc_cap and len(statements) > statements_per_doc_cap:
                step = len(statements) / statements_per_doc_cap
                statements = [
                    statements[int(i * step)] for i in range(statements_per_doc_cap)
                ]
            out.append({"doc_id": doc_id, "statements": statements, "count": len(statements)})
        return out

    def load_document(self, doc_id: str) -> List[Dict[str, Any]]:
        """Возвращает утверждения одного документа."""
        rows, _ = db.cypher_query(
            "MATCH (d:Document {uid: $doc_id})-[:HAS_STATEMENT]->(s:KnowledgeStatement) "
            "WHERE s.predicate IS NOT NULL AND NOT s.predicate IN $noise "
            "RETURN s.uid AS uid, s.subject_text AS subject_text, s.predicate AS predicate, "
            "s.object_text AS object_text, s.subject_type AS subject_type, "
            "s.object_type AS object_type, s.type AS type, s.confidence AS confidence "
            "ORDER BY s.sort_order",
            {"doc_id": doc_id, "noise": list(_NOISE)},
        )
        out = []
        for r in rows:
            out.append({
                "uid": r[0],
                "subject_text": r[1],
                "predicate": r[2],
                "object_text": r[3],
                "subject_type": r[4],
                "object_type": r[5],
                "type": r[6],
                "confidence": r[7],
            })
        return out

    def list_documents(self) -> List[Dict[str, Any]]:
        """Список документов с количеством утверждений (для выбора цели)."""
        rows, _ = db.cypher_query(
            "MATCH (d:Document)-[:HAS_STATEMENT]->(s:KnowledgeStatement) "
            "WHERE s.predicate IS NOT NULL AND NOT s.predicate IN $noise "
            "RETURN d.uid AS doc_id, count(s) AS cnt "
            "ORDER BY cnt DESC LIMIT 500",
            {"noise": list(_NOISE)},
        )
        return [{"doc_id": r[0], "statements_count": r[1]} for r in rows]

    # ── Проверка существующего знания (генерация) ──────────────────────────

    def check_statements(
        self,
        triplets: Sequence[Dict[str, Any]],
        *,
        doc_ids: Optional[Sequence[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Сверяет сгенерированные триплеты с существующими в корпусе.

        Для каждого триплета {subject_text, predicate, object_text} возвращает
        отчёт {"subject_text", "predicate", "object_text", "status", ...}, где
        status:
          * "new"      — утверждение отсутствует в БД;
          * "exists"   — полностью совпадает с существующим (subject/pred/object);
          * "conflicts"— существует утверждение с тем же субъектом и объектом,
                         но в *противоположном* направлении/аспекте (по
                         direction-свёртке предиката: increase vs decrease).

        Args:
            triplets: кандидаты (результат генерации).
            doc_ids: если задан — сверка только с этими документами; иначе по всему
                корпусу (утверждения применять ко всему корпусу).
        """
        if not triplets:
            return []
        # Нормализуем кандидатов
        cands: List[Dict[str, Any]] = []
        for t in triplets:
            cands.append({
                "subject_text": str(t.get("subject_text") or "").strip(),
                "predicate": str(t.get("predicate") or "").strip().lower(),
                "object_text": str(t.get("object_text") or "").strip(),
            })

        # Загружаем множество существующих (subject,predicate,object) + направление
        existing = self._load_exists_index(doc_ids=doc_ids)
        by_pair: Dict[Tuple[str, str], List[str]] = {}  # (subj,obj) -> [directions]
        exists_normal: Dict[Tuple[str, str, str], List[str]] = {}

        for row in existing:
            subj = row[0]
            pred = row[1]
            obj = row[2]
            doc = row[3]
            exists_normal.setdefault((subj, pred, obj), []).append(doc)
            direction = _direction_of(pred)
            if direction in {"up", "down"}:
                by_pair.setdefault((subj, obj), []).append(direction)
                by_pair.setdefault((obj, subj), []).append(_flip(direction))

        report: List[Dict[str, Any]] = []
        for c in cands:
            subj_key = c["subject_text"].lower()
            pred = c["predicate"]
            obj_key = c["object_text"].lower()
            exact = exists_normal.get((subj_key, pred, obj_key))
            if exact:
                report.append({
                    **c,
                    "status": "exists",
                    "check_mode": "exists",
                    "evidence_doc_ids": exact[:5],
                    "note": "Утверждение уже присутствует в базе.",
                })
                continue
            # конфликт: то же (субъект,объект), противоположное направление
            direction = _direction_of(pred)
            conflict = _find_conflict(by_pair, subj_key, obj_key, direction)
            if conflict:
                report.append({
                    **c,
                    "status": "conflicts",
                    "check_mode": "conflicts",
                    "conflicting_direction": conflict,
                    "evidence_doc_ids": [],
                    "note": (
                        f"Существует утверждение с тем же субъектом и объектом "
                        f"в противоположном направлении ('{conflict}')."
                    ),
                })
                continue
            report.append({
                **c,
                "status": "new",
                "check_mode": "new",
                "evidence_doc_ids": [],
                "note": "Новое утверждение — отсутствует в базе.",
            })
        return report

    def _load_exists_index(
        self,
        doc_ids: Optional[Sequence[str]] = None,
    ) -> List[Any]:
        """Загружает существующие утверждения корпуса: (subj, pred, obj, doc).

        ВАЖНО: не применяем _NOISE-фильтр — для сверки нового знания нужно видеть
        ВСЕ утверждения, включая категориальные (is_a/be/include).
        """
        query = (
            "MATCH (d:Document)-[:HAS_STATEMENT]->(s:KnowledgeStatement) "
            "WHERE s.predicate IS NOT NULL AND s.predicate <> '' "
        )
        params: Dict[str, Any] = {}
        if doc_ids:
            params["doc_ids"] = list(doc_ids)
            query += "AND d.uid IN $doc_ids "
        query += (
            "RETURN toLower(s.subject_text) AS subj, toLower(s.predicate) AS pred, "
            "toLower(s.object_text) AS obj, d.uid AS doc "
        )
        rows, _ = db.cypher_query(query, params)
        return rows

    def corpus_graphs(
        self,
        doc_ids: Optional[Sequence[str]] = None,
        predicate_mode: str = "raw",
        doc_limit: int = 200,
        statements_per_doc_cap: Optional[int] = None,
        max_nodes: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Графы утверждений корпуса — вход для gSpan-майнинга."""
        corpus = self.load_corpus(doc_ids=doc_ids, doc_limit=doc_limit,
                                  statements_per_doc_cap=statements_per_doc_cap)
        graphs = []
        for entry in corpus:
            graph = statements_to_graph(
                entry["doc_id"],
                entry["statements"],
                predicate_mode,
                max_nodes=max_nodes,
            )
            if graph["nodes"] and graph["edges"]:
                graphs.append(graph)
        return graphs


_default_repo: Optional[PatternMinerRepository] = None


def get_pattern_miner_repository() -> PatternMinerRepository:
    global _default_repo
    if _default_repo is None:
        _default_repo = PatternMinerRepository()
    return _default_repo
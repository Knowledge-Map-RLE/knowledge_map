"""
Layer: Service — Orchestration
Package: api.services.pattern_miner_service
Responsibility: оркестрация выявления паттернов по графу утверждений:
загрузка корпуса из Neo4j, майнинг частотных подграфов (gSpan) и наложение
паттерна на целевой граф результата поиска с генерацией кандидатов-пробелов.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Sequence

from adapters.repositories.pattern_miner_repository import PatternMinerRepository
from application.patterns.mine_statement_patterns import (
    mine_assertion_patterns,
    apply_pattern,
    target_graph_from_statements,
)
from application.generation import (
    LOGICAL,
    SYLLOGISM,
    THINKING,
    METHOD_LABELS,
    KNOWLEDGE_METHODS,
    method_metadata,
    run_generation,
)
from application.generation.provenance import build_knowledge_result, PATTERN

logger = logging.getLogger(__name__)

_UID_RE = re.compile(
    r"^(?:[0-9a-f]{8}[-]?[0-9a-f]{4}[-]?[0-9a-f]{4}[-]?[0-9a-f]{4}[-]?[0-9a-f]{12}|"
    r"[0-9a-f]{32}|[0-9a-f]{40}|[A-Za-z0-9+/]{40,})$"
)


def _is_meaningful(st: Dict[str, Any]) -> bool:
    """Пропускает только осмысленные утверждения для генерации знания."""
    subj = str(st.get("subject_text") or "").strip()
    obj = str(st.get("object_text") or "").strip()
    pred = str(st.get("predicate") or "").strip().lower()
    if not subj or not obj or not pred or pred in {"", "unknown"}:
        return False
    if len(subj) > 120 or len(obj) > 120:
        return False
    if _UID_RE.match(subj) or _UID_RE.match(obj):
        return False
    if any(t in subj or t in obj for t in ("http://", "https://", "doi.org", "www.", ".pdf")):
        return False
    return True


class PatternMinerService:
    def __init__(self, repo: Optional[PatternMinerRepository] = None) -> None:
        self.repo = repo or PatternMinerRepository()

    async def mine(
        self,
        *,
        doc_ids: Optional[Sequence[str]] = None,
        min_support: float = 0.3,
        min_size: int = 2,
        max_size: int = 6,
        limit: int = 200,
        predicate_mode: str = "raw",
        useful_only: bool = True,
        statements_per_doc_cap: Optional[int] = 140,
        max_nodes: Optional[int] = 120,
    ) -> Dict[str, Any]:
        """Выявление паттернов по структуре графа утверждений корпуса."""
        corpus = self.repo.load_corpus(
            doc_ids=doc_ids,
            statements_per_doc_cap=statements_per_doc_cap,
        )
        if not corpus:
            return {"success": True, "patterns": [], "corpus_size": 0,
                    "message": "В корпусе нет утверждений"}

        graphs = []
        for entry in corpus:
            graph = target_graph_from_statements(
                entry["doc_id"], entry["statements"], predicate_mode, max_nodes=max_nodes,
            )
            if graph["nodes"] and graph["edges"]:
                graphs.append(graph)

        if not graphs:
            return {"success": True, "patterns": [], "corpus_size": len(corpus),
                    "message": "Нет графов утверждений после фильтрации"}

        patterns = mine_assertion_patterns(
            graphs,
            min_support=min_support,
            min_size=min_size,
            max_size=max_size,
            limit=limit,
            useful_only=useful_only,
        )
        return {
            "success": True,
            "patterns": patterns,
            "corpus_size": len(graphs),
            "using_graphs": len(graphs),
            "params": {
                "min_support": min_support,
                "min_size": min_size,
                "max_size": max_size,
                "predicate_mode": predicate_mode,
                "statements_per_doc_cap": statements_per_doc_cap,
                "max_nodes": max_nodes,
            },
        }

    async def generate_all(
        self,
        *,
        predicate_mode: str = "raw",
        check_existing: bool = True,
        limit_per_method: int = 30,
        max_nodes: Optional[int] = 120,
        min_support: float = 0.3,
        min_size: int = 2,
        max_size: int = 6,
        statements_per_doc_cap: Optional[int] = 140,
        max_pool_size: int = 3000,
        corpus_doc_ids: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        """Автономная генерация нового знания всеми четырьмя способами.

        Способ применяется к утверждениям ВСЕГО корпуса (без выбора целевого
        документа). Алгоритм сам обходит все способы и их операции:
          * pattern   — майнит частотные структуры по корпусу gSpan'ом, затем
                        накладывает выявленные паттерны на графы корпуса и берёт
                        недостающие рёбра (gap-кандидаты) как новое знание;
          * logical   — все логические операции (транзитивность, обращение, …);
          * syllogism — все 24 модуса;
          * thinking  — все операции мышления.
        Каждый кандидат (для всех способов) сверяется с БД
        (new/exists/conflicts), если check_existing=True.
        """
        # ── пул утверждений всего корпуса (не шумовых — видим и категориальные) ──
        corpus = self.repo.load_corpus(
            doc_ids=corpus_doc_ids,
            statements_per_doc_cap=statements_per_doc_cap,
            noise_filter=False,
        )
        pool = [
            {
                "subject_text": st.get("subject_text"),
                "predicate": st.get("predicate"),
                "object_text": st.get("object_text"),
                "subject_type": st.get("subject_type"),
                "object_type": st.get("object_type"),
                "doc_id": entry.get("doc_id"),
            }
            for entry in corpus
            for st in entry.get("statements", [])
            if _is_meaningful(st)
        ]

        pool = pool[:max_pool_size]

        summary: List[Dict[str, Any]] = []
        # Сверка существующего знания ведётся по тому же корпусу, что участвовал
        # в генерации (не по всей БД размером в миллионы документов).
        check_scope: Optional[List[str]] = [e["doc_id"] for e in corpus]

        def _attach_checks(groups: List[Dict[str, Any]], scope: Optional[Sequence[str]] = None) -> None:
            # Единственный вызов репозитория на ВСЕ кандидаты всех групп
            # (иначе _load_exists_index выполнил бы полный MATCH по корпусу
            # на каждую группу — узкое место на реальных данных).
            all_new: List[Dict[str, Any]] = [
                n for r in groups for n in r.get("new_statements", [])
            ]
            checks = self.repo.check_statements(all_new, doc_ids=scope)
            by_key = {
                (c.get("subject_text", "").lower(), c.get("predicate", "").lower(),
                 c.get("object_text", "").lower()): c for c in checks
            }
            for r in groups:
                r["checks"] = []
                for n_stmt in r.get("new_statements", []):
                    key = (str(n_stmt.get("subject_text", "")).lower(),
                           str(n_stmt.get("predicate", "")).lower(),
                           str(n_stmt.get("object_text", "")).lower())
                    n_stmt["check"] = by_key.get(key)

        def _collect(method: str, groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            kept: List[Dict[str, Any]] = []
            for r in groups:
                ns = r.get("new_statements", [])
                fresh = [n for n in ns if _is_meaningful(n)]
                if not fresh:
                    continue
                r["new_statements"] = fresh
                kept.append(r)
            return kept

        # ── 1. PATTERN ─────────────────────────────────────────────────────
        pattern_groups: List[Dict[str, Any]] = []
        graphs = []
        for entry in corpus:
            graph = target_graph_from_statements(
                entry["doc_id"], entry["statements"], predicate_mode, max_nodes=max_nodes,
            )
            if graph["nodes"] and graph["edges"]:
                graphs.append(graph)
        if graphs:
            patterns = mine_assertion_patterns(
                graphs,
                min_support=min_support,
                min_size=min_size,
                max_size=max_size,
                limit=8,
                useful_only=True,
            )
            for pat in patterns[:4]:
                applied = [apply_pattern(g, pat)
                           for g in graphs
                           if g["nodes"] and len(g["nodes"]) <= 120]
                gaps: Dict[str, Dict[str, Any]] = {}
                for ap in applied:
                    for gap in ap.get("gaps", []):
                        key = (gap.get("subject_text", ""), gap.get("predicate", ""), gap.get("object_text", ""))
                        if not _is_meaningful(gap):
                            continue
                        gaps.setdefault(key, gap)
                        if len(gaps) >= limit_per_method * 4:
                            break
                    if len(gaps) >= limit_per_method * 4:
                        break
                if gaps:
                    pattern_groups.append(build_knowledge_result(
                        method=PATTERN,
                        operation=str(pat.get("id", "pattern")),
                        operation_label=f"Паттерн {pat.get('size', 0)} уз./{pat.get('edges_count', 0)} реб.",
                        source_statements=[],
                        new_statements=list(gaps.values())[:limit_per_method],
                        description=f"Недостающие рёбра, предложенные частотным паттерном "
                                    f"(поддержка {pat.get('support', 0)}).",
                    ))
        if pattern_groups:
            pattern_kept = _collect(PATTERN, pattern_groups)
            if check_existing:
                _attach_checks(pattern_kept, scope=check_scope)
            summary.append({"method": PATTERN, "label": METHOD_LABELS[PATTERN],
                            "count": sum(len(g["new_statements"]) for g in pattern_kept),
                            "groups": pattern_kept})

        # ── 2/3/4. LOGICAL + SYLLOGISM + THINKING ──────────────────────────
        for method in (LOGICAL, SYLLOGISM, THINKING):
            groups = run_generation(method=method, statements=pool, limit=limit_per_method * 4)
            kept = _collect(method, groups)
            if not kept:
                continue
            if check_existing:
                _attach_checks(kept, scope=check_scope)
            summary.append({"method": method, "label": METHOD_LABELS[method],
                            "count": sum(len(g["new_statements"]) for g in kept),
                            "groups": kept})

        return {
            "success": True,
            "message": "ok",
            "knowledge_method": "all",
            "corpus_size": len(corpus),
            "corpus_pool_size": len(pool),
            "methods": summary,
        }

    async def apply(
        self,
        *,
        doc_id: str,
        pattern: Dict[str, Any],
        predicate_mode: str = "raw",
        max_nodes: Optional[int] = 150,
        knowledge_method: str = "pattern",
        operation: Optional[str] = None,
        check_existing: bool = True,
        limit: int = 200,
        statements_per_doc_cap: Optional[int] = 140,
        corpus_doc_ids: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        """Наложение/генерация нового знания по выбранному способу.

        * При knowledge_method="pattern" — классическое наложение выбранного
          паттерна на граф целевого документа (как раньше).
        * При knowledge_method ∈ {logical, syllogism, thinking} — новые способы:
          операции выполняются над утверждениями ВСЕГО корпуса (или ограниченного
          corpus_doc_ids), и каждый кандидат сверяется с БД (new/exists/conflicts),
          если check_existing=True.
        """
        if knowledge_method not in KNOWLEDGE_METHODS:
            raise ValueError(f"Неизвестный способ генерации: {knowledge_method!r}")

        if knowledge_method == PATTERN:
            return await self._apply_pattern(
                doc_id=doc_id, pattern=pattern, predicate_mode=predicate_mode,
                max_nodes=max_nodes,
            )
        return await self._generate(
            knowledge_method=knowledge_method,
            operation=operation,
            check_existing=check_existing,
            limit=limit,
            statements_per_doc_cap=statements_per_doc_cap,
            doc_ids=corpus_doc_ids,
        )

    async def _apply_pattern(
        self,
        *,
        doc_id: str,
        pattern: Dict[str, Any],
        predicate_mode: str,
        max_nodes: Optional[int],
    ) -> Dict[str, Any]:
        """Классическое наложение паттерна на целевой документ."""
        statements = self.repo.load_document(doc_id)
        target = target_graph_from_statements(
            doc_id, statements, predicate_mode, max_nodes=max_nodes,
        )
        if not target["nodes"]:
            return {"success": False, "message": "У статьи нет утверждений",
                    "target_doc_id": doc_id, "result": None}

        result = apply_pattern(target, pattern)
        # добавляем цель для отображения на фронте
        result["target_doc_id"] = doc_id
        result["target_node_count"] = len(target["nodes"])
        result["target_edge_count"] = len(target["edges"])
        result["knowledge_method"] = PATTERN
        return {"success": True, "message": "ok", "target_doc_id": doc_id, "result": result}

    async def _generate(
        self,
        *,
        knowledge_method: str,
        operation: Optional[str],
        check_existing: bool,
        limit: int,
        statements_per_doc_cap: Optional[int],
        doc_ids: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        """Генерация нового знания методом (logical|syllogism|thinking) по всему корпусу."""
        corpus = self.repo.load_corpus(
            doc_ids=doc_ids,
            statements_per_doc_cap=statements_per_doc_cap,
            noise_filter=False,
        )
        # Собираем все утверждения корпуса в один пул (способ применяется ко всему корпусу),
        # отбрасывая «мусорные» тексты (URL, uid/hash, пустые, гигантские) — они не
        # дают осмысленного знания.
        pool: List[Dict[str, Any]] = []
        for entry in corpus:
            for st in entry.get("statements", []):
                if not _is_meaningful(st):
                    continue
                pool.append({
                    "subject_text": st.get("subject_text"),
                    "predicate": st.get("predicate"),
                    "object_text": st.get("object_text"),
                    "subject_type": st.get("subject_type"),
                    "object_type": st.get("object_type"),
                    "doc_id": entry.get("doc_id"),
                })

        if not pool:
            return {"success": False, "message": "В корпусе нет утверждений",
                    "result": None, "knowledge_method": knowledge_method}

        results = run_generation(
            method=knowledge_method,
            statements=pool,
            operation=operation,
            limit=limit,
        )
        if not results:
            return {"success": True, "message": "По этому способу/операции новых знаний не получено",
                    "knowledge_method": knowledge_method, "operation": operation,
                    "results": [], "corpus_size": len(corpus), "result": None}

        # Проверка существующих (по всему корпусу/выбранному подмножеству)
        if check_existing:
            check_scope = doc_ids
            for r in results:
                checks = self.repo.check_statements(r.get("new_statements", []), doc_ids=check_scope)
                r["checks"] = checks
                # прикрепляем проверку к каждому новому утверждению
                by_key = {
                    (c.get("subject_text", "").lower(),
                     c.get("predicate", "").lower(),
                     c.get("object_text", "").lower()): c
                    for c in checks
                }
                for n_stmt in r.get("new_statements", []):
                    key = (
                        str(n_stmt.get("subject_text", "")).lower(),
                        str(n_stmt.get("predicate", "")).lower(),
                        str(n_stmt.get("object_text", "")).lower(),
                    )
                    n_stmt["check"] = by_key.get(key)

        return {
            "success": True,
            "message": "ok",
            "knowledge_method": knowledge_method,
            "operation": operation,
            "results": results,
            "corpus_size": len(corpus),
            "corpus_pool_size": len(pool),
            "result": {
                "knowledge_method": knowledge_method,
                "operation": operation,
                "results": results,
                "corpus_size": len(corpus),
            },
        }

    async def metadata(self) -> Dict[str, Any]:
        """Способы и операции для UI."""
        return {"success": True, "methods": method_metadata()}

    async def list_documents(self) -> Dict[str, Any]:
        return {"success": True, "documents": self.repo.list_documents()}


_default_service: Optional[PatternMinerService] = None


def get_pattern_miner_service() -> PatternMinerService:
    global _default_service
    if _default_service is None:
        _default_service = PatternMinerService()
    return _default_service
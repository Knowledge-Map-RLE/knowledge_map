"""
Use case: выявление паттернов по структуре графа утверждений корпуса
и наложение паттерна на конкретный граф (целевая статья/результат поиска).

Майнинг делегируется алгоритмическому gSpan (services/gspan.py, частотные
связные подграфы). Здесь добавляется:

  * постфильтрация тривиальных/шумовых паттернов;
  * аннотирование паттернов примерами (реальные тексты из корпуса);
  * наложение паттерна на целевой граф с поиском «пробелов» — узлов и рёбер
    паттерна, которых не хватает в целевом графе, но контекст которых уже
    присутствует (кандидаты для генерации нового знания).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from services.gspan import (
    build_graph,
    canonical_key,
    graph_from_key,
    mine_frequent_subgraphs,
)

from application.patterns.statement_graph import (
    dedupe_graph_edges,
    statements_to_graph,
)

logger = logging.getLogger(__name__)

DIALECT_LABELS = {"concept", "statement", "literal", "_"}
# Тривиальные служебные предикаты (выдаются майнингом, но не полезны)
_TRIVIAL_PREDICATES = {"is_a", "contains", "related_to", "has"}


def _is_useful_pattern(p: Dict[str, Any], min_size: int) -> bool:
    """Паттерн полезен, если несёт нетривиальную структуру утверждений."""
    if p.get("size", 0) < min_size:
        return False
    edges = p.get("edges") or []
    if not edges:
        return False
    labels = {el for _, _, el in edges}
    return bool(labels - _TRIVIAL_PREDICATES)


def annotate_patterns_with_examples(
    patterns: List[Dict[str, Any]],
    corpus: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Добавляет паттернам примеры реальных утверждений из корпуса.

    Для каждого паттерна для support<=3 статей подбираются примеры триплетов,
    согласованных с метками рёбер/узлов паттерна.
    """
    # Индексируем raw-триплеты по нормализованному предикату
    by_pred: Dict[str, List[Dict[str, str]]] = {}
    for doc in corpus or []:
        for raw in doc.get("raw", []):
            key = raw.get("predicate", "").lower()
            by_pred.setdefault(key, []).append({**raw, "doc_id": doc.get("doc_id")})

    for p in patterns:
        pred = ""
        edges = p.get("edges") or []
        if edges:
            pred = edges[0][2]
        examples: List[Dict[str, str]] = []
        raw_key = pred.split(":", 1)[1] if ":" in pred else pred
        for e in by_pred.get(raw_key, [])[:5]:
            examples.append(e)
        p["examples"] = examples
    return patterns


def mine_assertion_patterns(
    corpus_graphs: Sequence[Dict[str, Any]],
    *,
    min_support: float = 0.3,
    min_size: int = 2,
    max_size: int = 6,
    limit: int = 200,
    useful_only: bool = True,
) -> List[Dict[str, Any]]:
    """Майнинг частотных паттернов утверждений по корпусу графов."""
    mined = mine_frequent_subgraphs(
        list(corpus_graphs),
        min_support=min_support,
        min_size=max(1, min_size),
        max_size=max_size,
        limit=limit * 20,
    )
    if useful_only:
        mined = [p for p in mined if _is_useful_pattern(p, min_size)]
    mined = mined[:limit]
    annotate_patterns_with_examples(mined, corpus_graphs)
    return mined


# ── Наложение паттерна на целевой граф ────────────────────────────────────

def _embedding_to_pattern_key(nodes: Sequence[str], edges: Sequence[Tuple[int, int, str]]) -> str:
    """Канонический ключ подпаттерна (для отчёта о совпадении)."""
    return "|".join(str(x) for x in canonical_key(list(nodes), list(edges)))


def find_partial_embeddings(
    target: Dict[str, Any],
    pattern_nodes: Sequence[str],
    pattern_edges: Sequence[Tuple[int, int, str]],
    require_any_edge: bool = True,
    max_embeddings: int = 20,
) -> List[Dict[str, Any]]:
    """Поиск частичных вложений паттерна в целевой граф.

    Частичное вложение — инъективное отображение всех узлов паттерна на узлы
    целого графа (совпадение по меткам), при котором подмножество рёбер
    паттерна найдено в цели, а остальные рёбра отсутствуют (пробелы).

    Returns:
        Список {
          "pattern_to_graph": {pattern_index: target_node_id},
          "matched_edges": [(i, j, label)],
          "missing_edges": [(i, j, label)],
          "matched_count": int, "missing_count": int,
          "complete": bool, "pattern_key": str
        }
    """
    target = dedupe_graph_edges(target)
    t_nodes = target.get("nodes") or []
    t_edges = target.get("edges") or []

    by_label: Dict[str, List[int]] = {}
    for ti, tn in enumerate(t_nodes):
        label = tn.get("label", "")
        by_label.setdefault(label, []).append(ti)

    edge_present: Dict[Tuple[int, int], Set[str]] = {}
    edge_idx: Dict[Tuple[int, int], int] = {}
    for ei, e in enumerate(t_edges):
        f, to, el = e.get("from"), e.get("to"), e.get("label")
        fi = next((i for i, n in enumerate(t_nodes) if n.get("id") == f), None)
        ti = next((i for i, n in enumerate(t_nodes) if n.get("id") == to), None)
        if fi is None or ti is None:
            continue
        edge_present.setdefault((fi, ti), set()).add(str(el))
        edge_idx[(fi, ti)] = ei

    n = len(pattern_nodes)
    mapping: List[Optional[int]] = [None] * n
    used: Set[int] = set()
    results: List[Dict[str, Any]] = []
    _stopped = False

    def matched_edge_set() -> List[Tuple[int, int, str]]:
        out = []
        for i, j, el in pattern_edges:
            mi, mj = mapping[i], mapping[j]
            if mi is None or mj is None:
                continue
            if el in edge_present.get((mi, mj), set()) or el in edge_present.get((mj, mi), set()):
                out.append((i, j, el))
        return out

    def missing_edge_set(matched: List[Tuple[int, int, str]]) -> List[Tuple[int, int, str]]:
        matched_set = set(matched)
        return [e for e in pattern_edges if e not in matched_set]

    def dfs(i: int) -> None:
        if i == n:
            matched = matched_edge_set()
            if require_any_edge and not matched:
                return
            missing = missing_edge_set(matched)
            # дедупликация эквивалентных вложений по ключу
            pat_key = _embedding_to_pattern_key(
                [pattern_nodes[k] for k in range(n)],
                [(a, b, c) for a, b, c in matched],
            )
            results.append({
                "pattern_to_graph": {str(k): t_nodes[m].get("id", "") for k, m in enumerate(mapping)},
                "matched_nodes": [t_nodes[m].get("id", "") for m in mapping],
                "matched_edges": [[a, b, c] for a, b, c in matched],
                "missing_edges": [[a, b, c] for a, b, c in missing],
                "matched_count": len(matched),
                "missing_count": len(missing),
                "complete": len(missing) == 0,
                "pattern_key": pat_key,
            })
            if len(results) >= max_embeddings:
                nonlocal _stopped
                _stopped = True
                return
            return

        label = pattern_nodes[i]
        candidates = by_label.get(label, [])[:6]
        for ti in candidates:
            if _stopped:
                return
            if ti in used:
                continue
            mapping[i] = ti
            used.add(ti)
            dfs(i + 1)
            used.remove(ti)
            mapping[i] = None

    dfs(0)

    # Эквивалентные вложения (одинаковый узловой состав) схлопываем
    unique: Dict[str, Dict[str, Any]] = {}
    for r in results:
        node_set = "|".join(sorted(str(v) for v in r["pattern_to_graph"].values()))
        key = (node_set, r["pattern_key"])
        existing = unique.get(key)
        if existing is None or r["missing_count"] < existing["missing_count"]:
            unique[key] = r
    return list(unique.values())


def build_gap_candidates(
    embedding: Dict[str, Any],
    target: Dict[str, Any],
    pattern_nodes: Sequence[str],
    pattern_edges: Sequence[Tuple[int, int, str]],
) -> List[Dict[str, Any]]:
    """Превращает отсутствующие рёбра вложения в кандидатов нового знания.

    Для каждого отсутствующего ребра паттерна (i->j, предикат el):
      src = целевой узел, на который спроецирована вершина i,
      dst = целевой узел, на который спроецирована вершина j.
    Кандидат = {subject_text: идентификатор узла src, predicate: el,
                object_text: идентификатор узла dst}, т.е. предложение нового
    утверждения, которого не хватает в целевом графе.
    """
    p2g = embedding.get("pattern_to_graph", {})
    id_to_text: Dict[str, str] = {}
    for node in target.get("nodes", []):
        id_to_text[node.get("id", "")] = node.get("id", "")
    node_text = target.get("node_text") or {}
    text_of = lambda nid: node_text.get(str(nid)) or id_to_text.get(str(nid), str(nid))

    candidates: List[Dict[str, Any]] = []
    for i, j, el in pattern_edges:
        src = p2g.get(str(i), "")
        dst = p2g.get(str(j), "")
        if not src or not dst:
            continue
        subject_text = text_of(src)
        object_text = text_of(dst)
        candidates.append({
            "subject_text": subject_text,
            "predicate": el,
            "object_text": object_text,
            "edge": [i, j, el],
        })
    return candidates


def apply_pattern(
    target: Dict[str, Any],
    pattern: Dict[str, Any],
) -> Dict[str, Any]:
    """Наложение выявленного паттерна на целевой граф утверждений.

    Returns:
        {
          "pattern": {id, size, edges_count, support, nodes, edges},
          "embeddings": [...],
          "gaps": [ кандидаты нового знания (build_gap_candidates) ],
          "complete_matches": int, "partial_matches": int,
        }
    """
    target = dedupe_graph_edges(target)
    pattern_nodes = [str(x) for x in pattern.get("nodes", [])]
    pattern_edges = [tuple(e) for e in pattern.get("edges", [])]
    embeddings = find_partial_embeddings(target, pattern_nodes, pattern_edges)
    gaps: List[Dict[str, Any]] = []
    for emb in embeddings:
        gaps.extend(build_gap_candidates(emb, target, pattern_nodes, pattern_edges))
    # дедупликация кандидатов
    seen: Set[Tuple[str, str, str]] = set()
    uniq: List[Dict[str, Any]] = []
    for g in gaps:
        key = (g.get("subject_text", ""), g.get("predicate", ""), g.get("object_text", ""))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(g)
    return {
        "pattern": {
            "id": pattern.get("id", ""),
            "size": pattern.get("size", 0),
            "edges_count": pattern.get("edges_count", 0),
            "support": pattern.get("support", 0),
            "nodes": list(pattern_nodes),
            "edges": [[a, b, c] for a, b, c in pattern_edges],
        },
        "embeddings": embeddings,
        "gaps": uniq,
        "complete_matches": sum(1 for e in embeddings if e.get("complete")),
        "partial_matches": sum(1 for e in embeddings if not e.get("complete")),
    }


def target_graph_from_statements(
    doc_id: str,
    statements: Sequence[Dict[str, Any]],
    predicate_mode: str = "raw",
    max_nodes: Optional[int] = None,
) -> Dict[str, Any]:
    """Целевой граф утверждений статьи для наложения паттерна."""
    return statements_to_graph(doc_id, statements, predicate_mode, max_nodes=max_nodes)


# ── Экспорт для удобства ──────────────────────────────────────────────────
__all__ = [
    "mine_assertion_patterns",
    "apply_pattern",
    "find_partial_embeddings",
    "build_gap_candidates",
    "target_graph_from_statements",
    "annotate_patterns_with_examples",
]
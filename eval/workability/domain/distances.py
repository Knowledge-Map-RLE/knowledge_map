"""
Domain — графовое расстояние между утверждениями.

KPI-2 требует топологического расстояния между состоянием знаний, из которого
сделано предсказание, и реально появившимся предсказанным утверждением.

Дизайн-решение: НЕВЗВЕШЕННЫЙ граф (все рёбра имеют вес 1), как согласовано.
Рёбра — BIBLIOGRAPHIC_LINK между статьями (source(cited) -> target(citing)),
загруженные на историческом snapshot (без утечки из будущего).

Расстояние считается на уровне статей: расстояние A -> B равно длине
кратчайшего пути по графу цитирования. Расстояние между утверждениями равно
минимальному расстоянию между их статьями (если несколько статей содержат
утверждение — берётся минимум). Утверждение, которого нет в снапшоте,
считается недостижимым (None).

Реализация — BFS на клиентской стороне: граф снапшота срезается локально, а не
через тяжёлые Cypher-запросы full-text по миллионам статей.
"""
from __future__ import annotations

from collections import deque
from typing import Dict, List, Optional, Set

from .statements import TemporalSnapshot


def build_doc_adjacency(
    snapshot: TemporalSnapshot,
) -> Dict[str, Set[str]]:
    """Строит ориентированный список смежности BIBLIOGRAPHIC_LINK снапшота.

    Args:
        snapshot: исторический граф (только данные <= T).

    Returns:
        dict: doc_id -> множество doc_id, достижимых одним шагом цитирования.
    """
    adj: Dict[str, Set[str]] = {}
    for src, tgt in snapshot.bibliographic_edges:
        adj.setdefault(src, set()).add(tgt)
    return adj


def shortest_path_docs(
    snapshot: TemporalSnapshot,
    source_doc: str,
    target_doc: str,
) -> Optional[int]:
    """Длина кратчайшего пути source_doc -> target_doc по невзвешенному графу.

    Возвращает:
        количество рёбер в кратчайшем пути, либо None, если путь отсутствует.
    """
    if source_doc == target_doc:
        return 0

    adj = build_doc_adjacency(snapshot)
    if source_doc not in adj:
        return None

    visited: Set[str] = {source_doc}
    queue: deque = deque([(source_doc, 0)])

    while queue:
        current, depth = queue.popleft()
        for nxt in adj.get(current, ()):
            if nxt == target_doc:
                return depth + 1
            if nxt not in visited:
                visited.add(nxt)
                queue.append((nxt, depth + 1))

    return None


def all_shortest_distances(
    snapshot: TemporalSnapshot,
    source_nk: str,
    targets: List[str],
    source_doc: Optional[str] = None,
) -> Dict[str, Optional[int]]:
    """Кратчайшие расстояния от source-утверждения до каждого target_nk.

    Модель: расстояние между утверждениями = min по статьям (расстояние между
    статьями по BIBLIOGRAPHIC_LINK). Один BFS из статей-источников даёт
    расстояния до всех целевых статей.

    Args:
        snapshot:     исторический граф (только данные <= T).
        source_nk:    норм-ключ исходного утверждения.
        targets:      норм-ключи целевых утверждений.
        source_doc:   (опционально) статья-контекст source (как в источнике
                      прогноза); если задана и содержит source_nk — источником
                      считается именно она. Иначе рассматриваются ВСЕ статьи,
                      содержащие source_nk.

    Returns:
        dict: target_nk -> расстояние (int) или None (недостижим).
    """
    result: Dict[str, Optional[int]] = {t: None for t in targets}
    if not source_nk or not targets:
        return result

    source_docs = snapshot.docs_for_statement(source_nk)
    if not source_docs:
        return result
    if source_doc and source_doc in source_docs:
        source_docs = {source_doc}

    # Целевые документы.
    target_docs: Set[str] = set()
    for t in targets:
        target_docs |= snapshot.docs_for_statement(t)
    if not target_docs:
        return result

    # Кратчайшие расстояния от любого источника до любого целевого документа.
    best: Dict[str, int] = {}
    adj = build_doc_adjacency(snapshot)

    for src in source_docs:
        if src in target_docs:
            best[src] = 0
        visited: Set[str] = {src}
        queue: deque = deque([(src, 0)])
        while queue:
            current, depth = queue.popleft()
            for nxt in adj.get(current, ()):
                if nxt in visited:
                    continue
                visited.add(nxt)
                nd = depth + 1
                if nxt in target_docs:
                    if nxt not in best or nd < best[nxt]:
                        best[nxt] = nd
                queue.append((nxt, nd))

    # Обратное отображение: target_nk -> min расстояние до его статей.
    for t in targets:
        t_docs = snapshot.docs_for_statement(t)
        d: Optional[int] = None
        for td in t_docs:
            if td in best:
                d = best[td] if d is None else min(d, best[td])
        result[t] = d
    return result
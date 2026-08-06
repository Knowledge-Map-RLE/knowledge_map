"""Frequent subgraph mining (FSM) over the full evidence subgraphs of articles.

Семейство gSpan: майнинг частотных связных подграфов в корпусе графов
(каждая статья представлена полным доказательственным подграфом EvidenceMap).
Подход:
  * каноническая форма подграфа — минимальная (по лексикографическому порядку
    кортежа) запись матрицы смежности среди всех перестановок вершин
    (точеный инвариант изоморфизма: изоморфные подграфы дают одинаковый ключ,
    неизоморфные — разные);
  * рост паттернов через расширение эмбеддингов: от каждого вхождения паттерна
    добавляется одно инцидентное ребро (новой вершиной или ребром между уже
    включёнными вершинами) — это полно для связных подграфов, т.к. у любого
    связного графа есть ребро, удаление которого сохраняет связность;
  * поддержка (support) — число графов корпуса, содержащих подграф (не число
    вхождений), что соответствует классическому определению частого подграфа.

Ограничения для прототипа: max_size <= 8 (перебор перестановок n! при
канонизации, при n > 9 становится медленным), мультиграфы не поддерживаются.
"""

from __future__ import annotations

import math
import logging
from dataclasses import dataclass, field
from itertools import permutations
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple, Union

logger = logging.getLogger(__name__)


# ── Внутреннее представление графа ─────────────────────────────────────────
class _Graph:
    """Неориентированный размеченный граф с целочисленными id вершин."""

    __slots__ = ("n", "vertex_labels", "adj", "edge_map", "orig_ids")

    def __init__(
        self,
        vertex_labels: List[str],
        edges: Iterable[Tuple[int, int, str]],
        orig_ids: Optional[List[str]] = None,
    ) -> None:
        self.n = len(vertex_labels)
        self.vertex_labels = list(vertex_labels)
        self.orig_ids = list(orig_ids) if orig_ids else [str(i) for i in range(self.n)]
        self.adj: Dict[int, List[Tuple[int, str]]] = {i: [] for i in range(self.n)}
        self.edge_map: Dict[Tuple[int, int], str] = {}
        for u, v, el in edges:
            self.add_edge(u, v, el)

    def add_edge(self, u: int, v: int, el: str) -> None:
        if u == v:
            return
        if v < u:
            u, v = v, u
        key = (u, v)
        if key in self.edge_map:
            # параллельные рёбра (разные метки) не поддерживаются — первое остаётся
            if self.edge_map[key] != el:
                logger.debug("Duplicate undirected edge %s ignored (parallel edges unsupported)", key)
            return
        self.edge_map[key] = el
        self.adj[u].append((v, el))
        self.adj[v].append((u, el))

    def has_edge(self, u: int, v: int, el: Optional[str] = None) -> bool:
        if u == v:
            return False
        if v < u:
            u, v = v, u
        found = self.edge_map.get((u, v))
        if found is None:
            return False
        return el is None or found == el

    def clone(self) -> "_Graph":
        return _Graph(list(self.vertex_labels), [(u, v, el) for (u, v), el in self.edge_map.items()])


def build_graph(
    graph: Dict[str, Any], id_key: str = "id", label_key: str = "label"
) -> _Graph:
    """Строит _Graph из внешнего представления {nodes, edges}.

    nodes: [{id: str, label: str}], edges: [{from: str, to: str, label: str}].
    """
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []
    id_to_idx: Dict[Any, int] = {}
    labels: List[str] = []
    orig_ids: List[str] = []
    for node in nodes:
        nid = node.get(id_key)
        if nid in id_to_idx:
            continue
        id_to_idx[nid] = len(labels)
        labels.append(str(node.get(label_key, "")))
        orig_ids.append(str(nid))
    edge_list: List[Tuple[int, int, str]] = []
    for e in edges:
        u = id_to_idx.get(e.get("from"))
        v = id_to_idx.get(e.get("to"))
        if u is None or v is None:
            continue
        edge_list.append((u, v, str(e.get(label_key, ""))))
    return _Graph(labels, edge_list, orig_ids)


# ── Каноническая форма ─────────────────────────────────────────────────────
_canonical_cache: Dict[Tuple[Any, ...], Tuple[Any, ...]] = {}
_CANONICAL_CACHE_LIMIT = 200000


def _norm_signature(
    vertices: Sequence[str], edges: Sequence[Tuple[int, int, str]]
) -> Tuple[Any, ...]:
    """Нормализованная подпись подграфа (не зависит от порядка рёбер/эмбеддинга).

    Используется как ключ кэша канонических форм: один и тот же подграф,
    достигнутый разными родителями или эмбеддингами, даёт одинаковую подпись.
    """
    eset = frozenset(
        (u, v, el) if u <= v else (v, u, el) for u, v, el in edges
    )
    return (tuple(vertices), eset)


def _canonical_best(vertices: Sequence[str], edges: Sequence[Tuple[int, int, str]]) -> Tuple[Tuple[Any, ...], Tuple[int, ...]]:
    """Минимальная лексикографическая запись подграфа среди всех перестановок вершин.

    Returns:
        (key, perm) — key: каноническая запись; perm: перестановка индексов
        входного порядка в канонический (perm[i] = входной индекс, стоящий на
        позиции i в каноническом порядке). Одинаковый ключ ⇔ изоморфизм.
    """
    n = len(vertices)
    if n > 9:
        raise ValueError(f"canonical_key supports n<=9, got {n}")
    emap: Dict[Tuple[int, int], str] = {}
    for u, v, el in edges:
        a, b = (u, v) if u <= v else (v, u)
        emap[(a, b)] = el
    best_key: Optional[Tuple[Any, ...]] = None
    best_perm: Optional[Tuple[int, ...]] = None
    for perm in permutations(range(n)):
        key: Tuple[Any, ...] = (n,) + tuple(vertices[p] for p in perm)
        key += tuple(
            emap.get(
                (min(perm[i], perm[j]), max(perm[i], perm[j])),
                "",
            )
            for i in range(n)
            for j in range(i + 1, n)
        )
        if best_key is None or key < best_key:
            best_key = key
            best_perm = perm
    return (best_key or ()), (best_perm or tuple(range(n)))


def canonical_key(vertices: Sequence[str], edges: Sequence[Tuple[int, int, str]]) -> Tuple[Any, ...]:
    """Минимальная лексикографически запись подграфа среди всех перестановок вершин.

    Ключ = (n, метки вершин в порядке перестановки, метки всех пар (i, j), i<j).
    Пустая метка пары означает отсутствие ребра. Одинаковый ключ ⇔ изоморфизм.
    Результат кэшируется по нормализованной подписи (порядок рёбер не важен).
    """
    signature = _norm_signature(vertices, edges)
    cached = _canonical_cache.get(signature)
    if cached is not None:
        return cached
    best_key, _ = _canonical_best(vertices, edges)
    if len(_canonical_cache) < _CANONICAL_CACHE_LIMIT:
        _canonical_cache[signature] = best_key
    return best_key


def graph_from_key(key: Tuple[Any, ...]) -> Tuple[List[str], List[Tuple[int, int, str]]]:
    """Обратное восстановление канонического представителя по ключу."""
    n = int(key[0])
    vertices = [str(x) for x in key[1 : 1 + n]]
    rest = key[1 + n :]
    edges: List[Tuple[int, int, str]] = []
    idx = 0
    for i in range(n):
        for j in range(i + 1, n):
            el = rest[idx]
            idx += 1
            if el:
                edges.append((i, j, str(el)))
    return vertices, edges


# ── Паттерн ────────────────────────────────────────────────────────────────
@dataclass
class Pattern:
    key: Tuple[Any, ...]
    vertices: List[str]
    edges: List[Tuple[int, int, str]]
    support: int = 0
    graphs: Set[str] = field(default_factory=set)
    embeddings: List[Tuple[int, Tuple[int, ...]]] = field(default_factory=list)
    _seen: Set[Tuple[int, Tuple[int, ...]]] = field(default_factory=set)

    @property
    def size(self) -> int:
        return len(self.vertices)

    @property
    def edge_count(self) -> int:
        return len(self.edges)


def _make_pattern(key: Tuple[Any, ...]) -> Pattern:
    vertices, edges = graph_from_key(key)
    return Pattern(key=key, vertices=vertices, edges=edges)


def _edge_set(p: Pattern) -> Set[Tuple[int, int]]:
    return {(u, v) if u <= v else (v, u) for u, v, _ in p.edges}


# ── Рост паттернов через эмбеддинги ────────────────────────────────────────
def _extend(p: Pattern, graphs: Sequence[_Graph], cand: Dict[Tuple[Any, ...], Pattern], cap: int, max_size: int) -> None:
    """Генерирует всех однорёберных суперграфов паттерна p.

    Сначала собираются РАЗЛИЧНЫЕ типы расширений (зависят только от меток и
    индексов вершин паттерна, а не от конкретного эмбеддинга):
      * backward: добавить ребро между двумя уже включёнными вершинами (a, b, el);
      * forward: добавить новую вершину с меткой lab, соединённую с вершиной pv
        ребром с меткой el — (pv, lab, el).
    Каноническая форма вычисляется ОДИН раз на тип расширения, затем к
    кандидату собираются поддерживающие эмбеддинги (для роста дальше).

    Backward-расширения не меняют размер (добавляют ребро внутри паттерна),
    поэтому выполняются и при p.size == max_size. Forward-расширения добавляют
    вершину — их при достижении max_size пропускаем.
    """
    npv = len(p.vertices)
    eset = _edge_set(p)

    bwd: Dict[Tuple[int, int, str], List[Tuple[int, Tuple[int, ...]]]] = {}
    fwd: Dict[Tuple[int, str, str], List[Tuple[int, Tuple[int, ...]]]] = {}
    for gidx, mapping in p.embeddings:
        g = graphs[gidx]
        inv: Dict[int, int] = {gv: pv for pv, gv in enumerate(mapping)}
        for pv in range(npv):
            gu = mapping[pv]
            for gw, el in g.adj[gu]:
                if gw in inv:
                    pv2 = inv[gw]
                    a, b = (pv, pv2) if pv <= pv2 else (pv2, pv)
                    if (a, b) in eset:
                        continue
                    bwd.setdefault((a, b, el), []).append((gidx, mapping))
                elif npv < max_size:
                    fwd.setdefault((pv, g.vertex_labels[gw], el), []).append(
                        (gidx, mapping + (gw,))
                    )

    for (a, b, el), embs in bwd.items():
        cand_vertices = p.vertices
        cand_edges = p.edges + [(a, b, el)]
        key, perm = _canonical_best(cand_vertices, cand_edges)
        np_ = cand.get(key)
        if np_ is None:
            np_ = _make_pattern(key)
            cand[key] = np_
        for gidx, mapping in embs:
            seen = (gidx, tuple(mapping[perm[i]] for i in range(len(perm))))
            if len(np_._seen) < cap and seen not in np_._seen:
                np_._seen.add(seen)
                np_.embeddings.append(seen)

    for (pv, new_label, el), embs in fwd.items():
        cand_vertices = list(p.vertices) + [new_label]
        cand_edges = p.edges + [(pv, npv, el)]
        key, perm = _canonical_best(cand_vertices, cand_edges)
        np_ = cand.get(key)
        if np_ is None:
            np_ = _make_pattern(key)
            cand[key] = np_
        for gidx, mapping in embs:
            ext = mapping + (npv,)
            seen = (gidx, tuple(ext[perm[i]] for i in range(len(perm))))
            if len(np_._seen) < cap and seen not in np_._seen:
                np_._seen.add(seen)
                np_.embeddings.append(seen)


# ── Подграфовый изоморфизм (для матчинга) ─────────────────────────────────
def contains_pattern(g: _Graph, vertices: Sequence[str], edges: Sequence[Tuple[int, int, str]]) -> bool:
    """True, если g содержит подграф (vertices/edges) — поиск изоморфизма возвратом."""
    n = len(vertices)
    if n == 0:
        return True
    by_label: Dict[str, List[int]] = {}
    for v, lab in enumerate(g.vertex_labels):
        by_label.setdefault(lab, []).append(v)

    mapping: Dict[int, int] = {}

    def dfs(i: int, used: Set[int]) -> bool:
        if i == n:
            return True
        lab = vertices[i]
        for gv in by_label.get(lab, []):
            if gv in used:
                continue
            ok = True
            for a, b, el in edges:
                if a == i:
                    if b in mapping and not g.has_edge(gv, mapping[b], el):
                        ok = False
                        break
                elif b == i:
                    if a in mapping and not g.has_edge(mapping[a], gv, el):
                        ok = False
                        break
            if not ok:
                continue
            mapping[i] = gv
            used.add(gv)
            if dfs(i + 1, used):
                return True
            used.remove(gv)
            del mapping[i]
        return False

    return dfs(0, set())


# ── Публичный API ──────────────────────────────────────────────────────────
def mine_frequent_subgraphs(
    graphs: Sequence[Dict[str, Any]],
    min_support: Union[int, float] = 0.6,
    min_size: int = 2,
    max_size: int = 8,
    limit: int = 2000,
    embedding_cap: int = 5000,
    id_key: str = "id",
    label_key: str = "label",
) -> List[Dict[str, Any]]:
    """Майнинг частотных связных подграфов в корпусе графов.

    Args:
        graphs: список графов {"id": str, "nodes": [{id, label}], "edges": [{from, to, label}]}.
        min_support: порог поддержки. float 0<v<=1 — доля корпуса; int — абсолютный счёт.
        min_size: минимальное число вершин паттерна (1 — отдельные метки).
        max_size: максимальное число вершин паттерна (<=9).
        limit: ограничение на число возвращаемых паттернов.
        embedding_cap: ограничение на число сохраняемых эмбеддингов на паттерн.

    Returns:
        Список паттернов, отсортированных по (support desc, size desc, edges desc):
        [{"id", "size", "edges_count", "support", "support_ratio", "graphs",
          "nodes": [labels], "edges": [[u, v, label]]}]
    """
    internal: List[_Graph] = [build_graph(g, id_key=id_key, label_key=label_key) for g in graphs]
    ids = [str(g.get("id", i)) for i, g in enumerate(graphs)]
    n_corpus = len(internal)
    if n_corpus == 0:
        return []

    if isinstance(min_support, float):
        min_count = max(1, int(math.ceil(min_support * n_corpus)))
    else:
        min_count = int(min_support)
    min_count = max(1, min_count)

    if max_size > 9:
        max_size = 9

    # Уровень 1: одиночные вершины
    by_key: Dict[Tuple[Any, ...], Pattern] = {}
    for gidx, g in enumerate(internal):
        seen_labels: Set[str] = set()
        for v in range(g.n):
            lab = g.vertex_labels[v]
            if lab in seen_labels:
                continue
            seen_labels.add(lab)
            key = (1, lab)
            p = by_key.get(key)
            if p is None:
                p = _make_pattern(key)
                by_key[key] = p
            p.embeddings.append((gidx, (v,)))
            p._seen.add((gidx, (v,)))

    level: List[Pattern] = []
    for p in by_key.values():
        p.support = len({e[0] for e in p.embeddings})
        p.graphs = {ids[e[0]] for e in p.embeddings}
        if p.support >= min_count:
            level.append(p)

    results: List[Pattern] = []
    while level:
        cand: Dict[Tuple[Any, ...], Pattern] = {}
        for p in level:
            _extend(p, internal, cand, embedding_cap, max_size)
        next_level: List[Pattern] = []
        for key, np_ in cand.items():
            np_.support = len({e[0] for e in np_.embeddings})
            np_.graphs = {ids[e[0]] for e in np_.embeddings}
            if np_.support < min_count or np_.size > max_size:
                continue
            next_level.append(np_)
            if np_.size >= min_size:
                results.append(np_)
        level = next_level

    results.sort(key=lambda p: (-p.support, -p.size, -p.edge_count, p.key))
    if limit and limit > 0:
        results = results[:limit]

    out: List[Dict[str, Any]] = []
    for p in results:
        out.append(
            {
                "id": "|".join(str(x) for x in p.key),
                "size": p.size,
                "edges_count": p.edge_count,
                "support": p.support,
                "support_ratio": round(p.support / n_corpus, 4),
                "graphs": sorted(p.graphs),
                "nodes": list(p.vertices),
                "edges": [[u, v, el] for u, v, el in p.edges],
            }
        )
    return out


def match_graph(
    graph: Dict[str, Any],
    patterns: Sequence[Dict[str, Any]],
    id_key: str = "id",
    label_key: str = "label",
) -> List[Dict[str, Any]]:
    """Алгоритмический матчинг: какие паттерны содержатся в графе новой статьи.

    Returns:
        Список {"pattern": <идент. паттерна>, "nodes": [labels], "edges": [[u,v,label]],
                "size", "edges_count", "support"} для каждого паттерна, найденного в графе.
    """
    g = build_graph(graph, id_key=id_key, label_key=label_key)
    out: List[Dict[str, Any]] = []
    for pat in patterns:
        vertices = [str(x) for x in pat.get("nodes", [])]
        edges = [tuple(e) for e in pat.get("edges", [])]
        if not vertices:
            continue
        if contains_pattern(g, vertices, edges):
            out.append(
                {
                    "pattern": pat.get("id", ""),
                    "nodes": list(vertices),
                    "edges": [[u, v, el] for u, v, el in edges],
                    "size": len(vertices),
                    "edges_count": len(edges),
                    "support": pat.get("support", 0),
                }
            )
    return out

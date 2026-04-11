"""
Layer: Application (Use Cases) — Infrastructure helper
Package: application.patterns.graph_layout
Responsibility: Force-directed layout вычисление на сервере.

Использует networkx.spring_layout (Fruchterman-Reingold / force-directed)
для вычисления координат узлов графа. Сохраняет layout_x/layout_y в Neo4j.

Allowed imports: typing, logging, networkx, neomodel
Forbidden imports: fastapi, web
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

import networkx as nx
from neomodel import db

logger = logging.getLogger(__name__)


def compute_and_save_layout(
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
    *,
    iterations: int = 50,
    save_to_db: bool = True,
) -> Dict[str, Tuple[float, float]]:
    """
    Вычисляет force-directed layout для графа и опционально сохраняет в Neo4j.

    :param nodes: список dict с ключом 'uid'
    :param edges: список dict с ключами 'src_uid', 'tgt_uid'
    :param iterations: число итераций spring_layout
    :param save_to_db: если True — сохраняет layout_x/layout_y в Neo4j
    :return: dict {uid: (x, y)} с координатами
    """
    if not nodes:
        return {}

    uid_set = {n["uid"] for n in nodes}

    # Строим graph
    G = nx.Graph()
    for n in nodes:
        G.add_node(n["uid"])

    for e in edges:
        src, tgt = e["src_uid"], e["tgt_uid"]
        if src in uid_set and tgt in uid_set:
            G.add_edge(src, tgt)

    # Определяем k (optimal distance) и scale
    n_nodes = len(nodes)
    # Для больших графов уменьшаем k чтобы узлы были плотнее
    k = 2.0 if n_nodes > 5000 else 1.0

    pos = nx.spring_layout(
        G,
        k=k,
        iterations=iterations,
        seed=42,
        threshold=1e-4,
    )

    # Масштабируем координаты для лучшей видимости
    if pos:
        xs = [p[0] for p in pos.values()]
        ys = [p[1] for p in pos.values()]
        x_range = max(xs) - min(xs) if xs else 1
        y_range = max(ys) - min(ys) if ys else 1
        scale = max(x_range, y_range, 1)
        # Нормализуем в диапазон [-500, 500]
        canvas = 500
        for uid in pos:
            x, y = pos[uid]
            pos[uid] = (
                (x - min(xs)) / scale * canvas * 2 - canvas,
                (y - min(ys)) / scale * canvas * 2 - canvas,
            )

    # Сохраняем в Neo4j
    if save_to_db and pos:
        _save_positions(pos)

    logger.info(f"[graph_layout] computed layout для {len(pos)} узлов")
    return pos


def _save_positions(positions: Dict[str, Tuple[float, float]]) -> None:
    """Batch-update layout_x/layout_y для Action и LexicalUnit."""
    # Разделяем по типу узла
    action_rows = []
    lexical_rows = []

    for uid, (x, y) in positions.items():
        # Определяем тип по длине uid (Action uid короче) или через запрос
        # Надёжнее — проверить в какой таблице есть uid
        action_rows.append({"uid": uid, "x": round(x, 2), "y": round(y, 2)})
        # На самом деле нужно определить тип — сделаем универсальный запрос
        lexical_rows.append({"uid": uid, "x": round(x, 2), "y": round(y, 2)})

    # Универсальный подход: обновляем оба типа, WHERE uid IN ...
    cypher = """
    MATCH (n)
    WHERE n.uid IN $uids
    AND (n:Action OR n:LexicalUnit)
    SET n.layout_x = $coords[n.uid].x,
        n.layout_y = $coords[n.uid].y
    RETURN count(n)
    """

    # Batch по 5000
    batch_size = 5000
    all_uids = list(positions.keys())

    coords_map = {uid: {"x": round(x, 2), "y": round(y, 2)} for uid, (x, y) in positions.items()}

    for i in range(0, len(all_uids), batch_size):
        batch_uids = all_uids[i : i + batch_size]
        batch_coords = {uid: coords_map[uid] for uid in batch_uids}
        try:
            db.cypher_query(cypher, {"uids": batch_uids, "coords": batch_coords})
        except Exception as e:
            logger.warning(f"[graph_layout] Ошибка сохранения позиций: {e}")

"""
Layer: Domain (Entities) — Business Rules
Package: domain.rules.graph_acyclicity
Responsibility: Проверка ацикличности ориентированного графа перед добавлением связи.

Принадлежит слою Domain, потому что это чистое бизнес-правило — алгоритм не зависит
ни от базы данных, ни от HTTP. Получает данные через callable, поэтому полностью
тестируется без Neo4j.

Извлечено из Block._is_acyclic() в src/models.py.

Allowed imports: только стандартная библиотека Python
Forbidden imports: neomodel, fastapi, grpc, aioboto3, application, adapters, infrastructure
"""
from __future__ import annotations

from collections import deque
from typing import Callable, List


def would_create_cycle(
    source_id: str,
    target_id: str,
    get_neighbors: Callable[[str], List[str]],
) -> bool:
    """
    Проверяет, создаст ли новая связь source → target цикл в DAG.

    Алгоритм: итеративный DFS от target, проверяет, достижим ли source.
    Если source достижим из target, значит добавление связи source→target создаст цикл.

    Args:
        source_id: ID исходного узла новой связи.
        target_id: ID целевого узла новой связи.
        get_neighbors: callable(node_id) → List[str] — возвращает ID исходящих соседей.
            Реализацию предоставляет репозиторий; правило не знает о хранилище.

    Returns:
        True если добавление связи создаст цикл, False если граф останется ацикличным.
    """
    visited: set[str] = set()
    stack: deque[str] = deque([target_id])

    while stack:
        node_id = stack.pop()

        if node_id == source_id:
            return True  # Достигли source — цикл

        if node_id in visited:
            continue

        visited.add(node_id)

        for neighbor_id in get_neighbors(node_id):
            if neighbor_id not in visited:
                stack.append(neighbor_id)

    return False

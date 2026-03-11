"""
Layer: Application (Use Cases)
Package: application.links.create_link
Responsibility: Создаёт связь между блоками с проверкой ацикличности.

Принадлежит слою Application. Оркестрирует: проверку наличия блоков →
проверку ацикличности через domain rule → создание связи через репозиторий.

Allowed imports: domain.*, application.ports.repositories
Forbidden imports: fastapi, neomodel, infrastructure, web
"""
from __future__ import annotations

from domain.models.block import LinkRecord
from domain.exceptions import NotFoundError, CyclicGraphError
from domain.rules.graph_acyclicity import would_create_cycle
from application.ports.repositories import BlockRepositoryProtocol, LinkRepositoryProtocol


def create_link(
    block_repo: BlockRepositoryProtocol,
    link_repo: LinkRepositoryProtocol,
    source_id: str,
    target_id: str,
) -> LinkRecord:
    """
    Создаёт связь source → target.

    Raises:
        NotFoundError: один из блоков не найден.
        CyclicGraphError: создание связи привело бы к циклу.
    """
    source = block_repo.get_by_id(source_id)
    if source is None:
        raise NotFoundError("Block", source_id)

    target = block_repo.get_by_id(target_id)
    if target is None:
        raise NotFoundError("Block", target_id)

    # Передаём callable репозитория в чистую функцию — domain rule не знает о Neo4j
    if would_create_cycle(
        source_id=source_id,
        target_id=target_id,
        get_neighbors=block_repo.get_outgoing_neighbor_ids,
    ):
        raise CyclicGraphError(source_id, target_id)

    return link_repo.create(source_id, target_id)

"""
Layer: Application (Use Cases)
Package: application.blocks.delete_block
Responsibility: Удаляет блок и все связанные с ним связи.

Allowed imports: domain.*, application.ports.repositories
Forbidden imports: fastapi, neomodel, infrastructure, web
"""
from __future__ import annotations

from domain.exceptions import NotFoundError
from application.ports.repositories import BlockRepositoryProtocol


def delete_block(repo: BlockRepositoryProtocol, block_id: str) -> None:
    """
    Удаляет блок. Репозиторий сам удаляет связи.

    Raises:
        NotFoundError: если блок не найден.
    """
    block = repo.get_by_id(block_id)
    if block is None:
        raise NotFoundError("Block", block_id)
    repo.delete(block_id)

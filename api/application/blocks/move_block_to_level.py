"""
Layer: Application (Use Cases)
Package: application.blocks.move_block_to_level
Responsibility: Перемещает закреплённый блок на указанный уровень.

Allowed imports: domain.*, application.ports.repositories
Forbidden imports: fastapi, neomodel, infrastructure, web
"""
from __future__ import annotations

from domain.models.block import Block
from domain.exceptions import NotFoundError, BlockNotPinnedError
from application.ports.repositories import BlockRepositoryProtocol


def move_block_to_level(
    repo: BlockRepositoryProtocol,
    block_id: str,
    target_level: int,
) -> Block:
    """
    Перемещает блок на target_level.

    Raises:
        NotFoundError: блок не найден.
        BlockNotPinnedError: блок не закреплён.
    """
    block = repo.get_by_id(block_id)
    if block is None:
        raise NotFoundError("Block", block_id)
    if not block.is_pinned:
        raise BlockNotPinnedError(block_id)
    block.level = target_level
    return repo.save(block)

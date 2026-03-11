"""
Layer: Application (Use Cases)
Package: application.blocks.update_block
Responsibility: Обновляет содержимое существующего блока.

Allowed imports: domain.*, application.ports.repositories
Forbidden imports: fastapi, neomodel, infrastructure, web
"""
from __future__ import annotations

from domain.models.block import Block
from domain.exceptions import NotFoundError
from application.ports.repositories import BlockRepositoryProtocol


def update_block(repo: BlockRepositoryProtocol, block_id: str, content: str) -> Block:
    """
    Обновляет content блока.

    Raises:
        NotFoundError: если блок с block_id не существует.
    """
    block = repo.get_by_id(block_id)
    if block is None:
        raise NotFoundError("Block", block_id)
    block.content = content
    return repo.save(block)

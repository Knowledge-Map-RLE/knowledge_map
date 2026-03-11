"""
Layer: Application (Use Cases)
Package: application.blocks.create_block
Responsibility: Создаёт новый блок в графе знаний.

Allowed imports: domain.*, application.ports.repositories
Forbidden imports: fastapi, neomodel, grpc, infrastructure, web
"""
from __future__ import annotations

from domain.models.block import Block
from application.ports.repositories import BlockRepositoryProtocol


def create_block(
    repo: BlockRepositoryProtocol,
    content: str,
    layer: int = 0,
) -> Block:
    """
    Создаёт и сохраняет новый блок.

    Returns:
        Сохранённый Block с присвоенным uid.
    """
    block = Block(uid="", content=content, layer=layer)
    return repo.save(block)

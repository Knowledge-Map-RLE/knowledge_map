"""
Layer: Application (Use Cases)
Package: application.blocks.pin_block
Responsibility: Закрепляет блок за уровнем (с опциональным физическим масштабом).

Allowed imports: domain.*, application.ports.repositories, application.ports.layout_gateway
Forbidden imports: fastapi, neomodel, infrastructure, web
"""
from __future__ import annotations

from typing import Optional, Dict, Any

from domain.models.block import Block
from domain.exceptions import NotFoundError
from application.ports.repositories import BlockRepositoryProtocol
from application.ports.layout_gateway import LayoutGatewayProtocol


async def pin_block(
    block_repo: BlockRepositoryProtocol,
    layout_gateway: LayoutGatewayProtocol,
    block_id: str,
    physical_scale: Optional[int] = None,
) -> Block:
    """
    Закрепляет блок. Если level == 0, определяет его из текущей укладки.

    Raises:
        NotFoundError: блок не найден.
    """
    block = block_repo.get_by_id(block_id)
    if block is None:
        raise NotFoundError("Block", block_id)

    if block.level == 0:
        all_blocks, all_links = block_repo.get_all_with_links()
        blocks_for_layout = [
            {"id": b.uid, "content": b.content, "layer": b.layer, "level": b.level,
             "is_pinned": b.is_pinned, "physical_scale": b.physical_scale, "metadata": {}}
            for b in all_blocks
        ]
        links_for_layout = [
            {"id": l.uid, "source_id": l.source_id, "target_id": l.target_id}
            for l in all_links
        ]
        layout_result = await layout_gateway.calculate_layout(blocks_for_layout, links_for_layout)

        if layout_result.get("success") and layout_result.get("blocks"):
            for b_info in layout_result["blocks"]:
                if b_info["id"] == block_id:
                    block.level = b_info.get("level", 0)
                    break

    block.is_pinned = True
    if physical_scale is not None:
        block.physical_scale = physical_scale

    return block_repo.save(block)


async def unpin_block(
    block_repo: BlockRepositoryProtocol,
    block_id: str,
) -> Block:
    """
    Открепляет блок от уровня.

    Raises:
        NotFoundError: блок не найден.
    """
    block = block_repo.get_by_id(block_id)
    if block is None:
        raise NotFoundError("Block", block_id)
    block.is_pinned = False
    return block_repo.save(block)

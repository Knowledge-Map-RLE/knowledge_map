"""
Layer: Application (Use Cases)
Package: application.blocks.create_block_and_link
Responsibility: Атомарно создаёт новый блок, связь с существующим и пересчитывает укладку.

Allowed imports: domain.*, application.ports.repositories, application.ports.layout_gateway
Forbidden imports: fastapi, neomodel, grpc, infrastructure, web
"""
from __future__ import annotations

from typing import Dict, Any

from domain.models.block import Block
from domain.exceptions import NotFoundError
from application.ports.repositories import BlockRepositoryProtocol, LinkRepositoryProtocol
from application.ports.layout_gateway import LayoutGatewayProtocol


async def create_block_and_link(
    block_repo: BlockRepositoryProtocol,
    link_repo: LinkRepositoryProtocol,
    layout_gateway: LayoutGatewayProtocol,
    source_block_id: str,
    new_block_content: str,
    link_direction: str,  # 'from_source' | 'to_source'
) -> Dict[str, Any]:
    """
    Создаёт новый блок и связь. Пересчитывает укладку графа.

    Returns:
        dict с ключами: new_block (dict), new_link (dict), layout (dict)

    Raises:
        NotFoundError: если source_block не найден.
    """
    source = block_repo.get_by_id(source_block_id)
    if source is None:
        raise NotFoundError("Block", source_block_id)

    new_block = block_repo.save(
        Block(uid="", content=new_block_content, layer=source.layer + 1)
    )

    if link_direction == "from_source":
        link = link_repo.create(source.uid, new_block.uid)
    else:
        link = link_repo.create(new_block.uid, source.uid)

    # Получаем весь граф для пересчёта укладки
    all_blocks, all_links = block_repo.get_all_with_links()
    blocks_for_layout = [
        {
            "id": b.uid,
            "content": b.content,
            "layer": b.layer,
            "level": b.level,
            "is_pinned": b.is_pinned,
            "physical_scale": b.physical_scale,
            "metadata": {},
        }
        for b in all_blocks
    ]
    links_for_layout = [
        {"id": l.uid, "source_id": l.source_id, "target_id": l.target_id}
        for l in all_links
    ]

    layout_result = await layout_gateway.calculate_layout(blocks_for_layout, links_for_layout)

    new_block_data = next(
        (b for b in layout_result.get("blocks", []) if b["id"] == new_block.uid),
        {"id": new_block.uid, "content": new_block.content, "level": 0},
    )

    return {
        "new_block": new_block_data,
        "new_link": {
            "id": link.uid,
            "source_id": link.source_id,
            "target_id": link.target_id,
        },
        "layout": layout_result,
    }

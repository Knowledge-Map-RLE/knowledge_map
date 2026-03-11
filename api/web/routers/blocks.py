"""
Layer: Interface Adapters — Controller (Web)
Package: web.routers.blocks
Responsibility: HTTP route handlers для операций с блоками. Тонкий контроллер.

Принадлежит слою web. Только парсинг запроса → вызов use case → ответ.
Бизнес-логика в application/blocks/. Доменные исключения → web/exception_handlers.py.

Allowed imports: fastapi, application.blocks.*, web.dependencies, src.schemas.api
Forbidden imports: neomodel (напрямую), services (напрямую), infrastructure
"""
import logging
from typing import Dict, Any

from fastapi import APIRouter, Depends

from src.schemas.api import BlockInput, CreateAndLinkInput, MoveToLevelInput, PinWithScaleInput
from application.blocks.create_block import create_block
from application.blocks.update_block import update_block
from application.blocks.delete_block import delete_block
from application.blocks.create_block_and_link import create_block_and_link
from application.blocks.pin_block import pin_block, unpin_block
from application.blocks.move_block_to_level import move_block_to_level
from web.dependencies import get_block_repository, get_link_repository, get_layout_client_dep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/blocks", tags=["blocks"])


@router.post("", response_model=Dict[str, Any])
async def create_block_route(block_input: BlockInput, repo=Depends(get_block_repository)):
    block = create_block(repo=repo, content=block_input.content)
    return {
        "success": True,
        "block": {
            "id": block.uid,
            "content": block.content,
            "level": block.level,
            "layer": block.layer,
            "sublevel_id": block.sublevel_id,
            "is_pinned": block.is_pinned,
            "physical_scale": block.physical_scale,
        },
    }


@router.put("/{block_id}", response_model=Dict[str, Any])
async def update_block_route(
    block_id: str, block_input: BlockInput, repo=Depends(get_block_repository)
):
    block = update_block(repo=repo, block_id=block_id, content=block_input.content)
    return {
        "success": True,
        "block": {
            "id": block.uid,
            "content": block.content,
            "level": block.level,
            "layer": block.layer,
            "sublevel_id": block.sublevel_id,
            "is_pinned": block.is_pinned,
            "physical_scale": block.physical_scale,
        },
    }


@router.post("/create_and_link", response_model=Dict[str, Any])
async def create_block_and_link_route(
    data: CreateAndLinkInput,
    block_repo=Depends(get_block_repository),
    link_repo=Depends(get_link_repository),
    layout_client=Depends(get_layout_client_dep),
):
    result = await create_block_and_link(
        block_repo=block_repo,
        link_repo=link_repo,
        layout_gateway=layout_client,
        source_block_id=data.source_block_id,
        new_block_content=data.new_block_content,
        link_direction=data.link_direction,
    )
    return {"success": True, **result}


@router.delete("/{block_id}", response_model=Dict[str, Any])
async def delete_block_route(block_id: str, repo=Depends(get_block_repository)):
    delete_block(repo=repo, block_id=block_id)
    return {"success": True, "message": f"Block {block_id} deleted successfully"}


@router.post("/{block_id}/pin", response_model=Dict[str, Any])
async def pin_block_route(
    block_id: str,
    block_repo=Depends(get_block_repository),
    layout_client=Depends(get_layout_client_dep),
):
    logger.info(f"PIN_BLOCK CALLED: {block_id}")
    block = await pin_block(
        block_repo=block_repo,
        layout_gateway=layout_client,
        block_id=block_id,
    )
    return {"success": True, "message": f"Block {block_id} pinned at level {block.level}"}


@router.post("/{block_id}/unpin", response_model=Dict[str, Any])
async def unpin_block_route(block_id: str, block_repo=Depends(get_block_repository)):
    await unpin_block(block_repo=block_repo, block_id=block_id)
    return {"success": True, "message": f"Block {block_id} unpinned successfully"}


@router.post("/{block_id}/pin_with_scale", response_model=Dict[str, Any])
async def pin_block_with_scale_route(
    block_id: str,
    data: PinWithScaleInput,
    block_repo=Depends(get_block_repository),
    layout_client=Depends(get_layout_client_dep),
):
    logger.info(f"PIN_BLOCK_WITH_SCALE CALLED: {block_id} scale={data.physical_scale}")
    block = await pin_block(
        block_repo=block_repo,
        layout_gateway=layout_client,
        block_id=block_id,
        physical_scale=data.physical_scale,
    )
    return {
        "success": True,
        "message": f"Block {block_id} pinned at level {block.level} scale {data.physical_scale}",
    }


@router.post("/{block_id}/move_to_level", response_model=Dict[str, Any])
async def move_block_route(
    block_id: str,
    data: MoveToLevelInput,
    repo=Depends(get_block_repository),
):
    logger.info(f"MOVE_BLOCK_TO_LEVEL CALLED: {block_id} -> {data.target_level}")
    move_block_to_level(repo=repo, block_id=block_id, target_level=data.target_level)
    return {"success": True, "message": f"Block {block_id} moved to level {data.target_level}"}

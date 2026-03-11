"""
Layer: Interface Adapters — Controller (Web)
Package: web.routers.links
Responsibility: HTTP route handlers для операций со связями. Тонкий контроллер.

Allowed imports: fastapi, application.links.*, web.dependencies, src.schemas.api
Forbidden imports: neomodel (напрямую), services (напрямую), infrastructure
"""
import logging
from typing import Dict, Any

from fastapi import APIRouter, Depends

from src.schemas.api import LinkInput
from application.links.create_link import create_link
from application.links.delete_link import delete_link
from web.dependencies import get_block_repository, get_link_repository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/links", tags=["links"])


@router.post("", response_model=Dict[str, Any])
async def create_link_route(
    link_input: LinkInput,
    block_repo=Depends(get_block_repository),
    link_repo=Depends(get_link_repository),
):
    link = create_link(
        block_repo=block_repo,
        link_repo=link_repo,
        source_id=link_input.source,
        target_id=link_input.target,
    )
    return {
        "success": True,
        "link": {"id": link.uid, "source_id": link.source_id, "target_id": link.target_id},
    }


@router.delete("/{link_id}", response_model=Dict[str, Any])
async def delete_link_route(link_id: str, link_repo=Depends(get_link_repository)):
    delete_link(repo=link_repo, link_id=link_id)
    return {"success": True, "message": f"Link {link_id} deleted successfully"}

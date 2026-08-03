import logging
from fastapi import APIRouter
from . import articles, parse, graph, split_blocks, images

logger = logging.getLogger(__name__)

router = APIRouter(tags=["article_editor"])

router.include_router(articles.router, prefix="")
router.include_router(parse.router, prefix="")
router.include_router(graph.router, prefix="")
router.include_router(split_blocks.router, prefix="")
router.include_router(images.router, prefix="")

__all__ = ["router"]

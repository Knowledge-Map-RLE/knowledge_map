"""Роутер для работы с укладкой графов"""
import logging
from typing import Dict, Any

from fastapi import APIRouter, HTTPException

from src.schemas.api import LayoutRequest, ViewportBounds, ViewportEdgesResponse
from services.layout_service import LayoutService
from services import get_layout_client, LayoutOptions

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/layout", tags=["layout"])
layout_service = LayoutService()


@router.get("/health")
async def check_layout_health():
    """Проверяет здоровье сервиса укладки"""
    try:
        client = get_layout_client()
        is_healthy = await client.health_check()
        if is_healthy:
            return {"status": "ok", "message": "Layout service is healthy"}
        else:
            return {"status": "error", "message": "Layout service is not healthy"}, 503
    except Exception as e:
        logger.error(f"Layout health check error: {e}")
        return {"status": "error", "message": str(e)}, 503


@router.post("")
async def calculate_layout(request: LayoutRequest) -> Dict[str, Any]:
    """Рассчитывает укладку для заданного графа"""
    try:
        client = get_layout_client()
        
        # Преобразуем запрос в формат для сервиса укладки
        blocks = [
            {
                "id": block.id,
                "content": block.content,
                "metadata": block.metadata
            }
            for block in request.blocks
        ]
        
        links = [
            {
                "id": link.id,
                "source_id": link.source_id,
                "target_id": link.target_id,
                "metadata": link.metadata
            }
            for link in request.links
        ]
        
        # Настройки алгоритма
        options = LayoutOptions(
            sublevel_spacing=request.sublevel_spacing,
            layer_spacing=request.layer_spacing,
            optimize_layout=request.optimize_layout
        )
        
        # Получаем укладку
        result = await client.calculate_layout(blocks, links, options)
        
        # Проверяем результат
        if not result.get("success", False):
            error_msg = result.get("error", "Неизвестная ошибка при расчете укладки")
            logger.error(f"Layout calculation error: {error_msg}")
            raise HTTPException(status_code=500, detail=error_msg)
        
        return result
        
    except Exception as e:
        logger.error(f"Layout calculation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/articles")
async def get_articles_layout() -> Dict[str, Any]:
    """Получает укладку только для статей (блоков с типом "Article")"""
    return await layout_service.get_articles_layout()


@router.post("/api/articles/edges_by_viewport", response_model=ViewportEdgesResponse)
async def get_edges_by_viewport(bounds: ViewportBounds, limit_per_node: int = 200):
    """Возвращает узлы в окне и рёбра, у которых хотя бы один конец попадает в окно."""
    bounds_dict = bounds.model_dump()
    result = await layout_service.get_edges_by_viewport(bounds_dict, limit_per_node)
    return ViewportEdgesResponse(**result)


@router.get("/articles_all")
async def get_all_articles_layout() -> Dict[str, Any]:
    """Возвращает все блоки и связи из графа статей."""
    return await layout_service.get_all_articles_layout()


@router.get("/articles_page")
async def get_articles_layout_page(
    offset: int = 0,
    limit: int = 2000,
    center_x: float = 0.0,
    center_y: float = 0.0,
) -> Dict[str, Any]:
    """Возвращает часть графа статей, упорядоченную по близости к (center_x, center_y)."""
    return await layout_service.get_articles_layout_page(offset, limit, center_x, center_y)


@router.get("/neo4j")
async def get_layout_from_neo4j(user_id: str = None) -> Dict[str, Any]:
    """Получает укладку из Neo4j для блоков Block"""
    return await layout_service.get_layout_from_neo4j(user_id)

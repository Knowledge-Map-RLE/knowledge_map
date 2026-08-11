"""
Layer: Interface Adapters — Web (Routers)
Package: routers.social_network
Responsibility: HTTP-контроллеры социальной сети (чат, друзья, сообщества,
профили, уведомления, тренды, жалобы). Тонкие, делегируют в
services.social_network_service.
"""
import logging

from fastapi import APIRouter

from . import chat, social, wall

logger = logging.getLogger(__name__)

router = APIRouter(tags=["social_network"])

router.include_router(chat.router, prefix="")
router.include_router(social.router, prefix="")
router.include_router(wall.router, prefix="")

__all__ = ["router"]

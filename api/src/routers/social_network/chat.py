"""
Layer: Interface Adapters — Web (Routers)
Package: routers.social_network.chat
Responsibility: HTTP-контроллеры чатов-обсуждений (статьи, триплеты, профили,
сообщества) и уведомлений. Все мутации требуют авторизации.
"""
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from services.social_network_service import SocialNetworkService
from web.dependencies import get_current_user, get_optional_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["social_network"])

service = SocialNetworkService()

_TARGET_TYPES = ("article", "statement", "user", "community")


class SendMessageRequest(BaseModel):
    text: str
    parent_uid: Optional[str] = None
    references: Optional[list[dict[str, Any]]] = None


@router.get("/social/chat/{target_type}/{target_uid}")
async def get_chat(
    target_type: str,
    target_uid: str,
    before: Optional[float] = None,
    limit: int = 50,
    user: Optional[dict] = Depends(get_optional_user),
):
    if target_type not in _TARGET_TYPES:
        raise HTTPException(status_code=400, detail="bad_target_type")
    return service.get_messages(
        target_type, target_uid, viewer_uid=(user or {}).get("uid"), before=before, limit=limit
    )


@router.post("/social/chat/{target_type}/{target_uid}")
async def send_message(
    target_type: str,
    target_uid: str,
    req: SendMessageRequest,
    user: dict = Depends(get_current_user),
):
    if target_type not in _TARGET_TYPES:
        raise HTTPException(status_code=400, detail="bad_target_type")
    result = service.send_message(
        author=user,
        target_type=target_type,
        target_uid=target_uid,
        text=req.text,
        parent_uid=req.parent_uid,
        references=req.references,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "send_failed"))
    return result


@router.post("/social/chat/messages/{message_uid}/like")
async def like_message(message_uid: str, user: dict = Depends(get_current_user)):
    result = service.toggle_like(user.get("uid", ""), message_uid)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "message_not_found"))
    return result


@router.get("/social/notifications")
async def get_notifications(user: dict = Depends(get_current_user)):
    return service.get_notifications(user.get("uid", ""))


class MarkReadRequest(BaseModel):
    notification_uid: Optional[str] = None


@router.post("/social/notifications/read")
async def mark_notifications_read(
    req: MarkReadRequest,
    user: dict = Depends(get_current_user),
):
    return service.mark_notifications_read(user.get("uid", ""), req.notification_uid)

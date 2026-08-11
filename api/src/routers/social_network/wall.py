"""
Layer: Interface Adapters — Web (Routers)
Package: routers.social_network.wall
Responsibility: HTTP-контроллеры стены профиля: чтение записей с комментариями,
создание записи (только владелец стены), добавление комментария (любой
авторизованный).
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from services.social_network_service import SocialNetworkService
from web.dependencies import get_current_user, get_optional_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["social_network"])

service = SocialNetworkService()


class CreateWallPostRequest(BaseModel):
    text: str


class AddWallCommentRequest(BaseModel):
    text: str


@router.get("/social/wall/{uid}")
async def get_wall(uid: str, user: Optional[dict] = Depends(get_optional_user)):
    result = service.get_wall(uid, viewer_uid=(user or {}).get("uid"))
    if result is None:
        raise HTTPException(status_code=404, detail="user_not_found")
    return result


@router.post("/social/wall/{uid}")
async def create_wall_post(
    uid: str,
    req: CreateWallPostRequest,
    user: dict = Depends(get_current_user),
):
    result = service.create_wall_post(user, uid, req.text)
    if not result.get("success"):
        code = 403 if result.get("error") == "forbidden" else 400
        raise HTTPException(status_code=code, detail=result.get("error", "create_failed"))
    return result


@router.post("/social/wall/posts/{post_uid}/comments")
async def add_wall_comment(
    post_uid: str,
    req: AddWallCommentRequest,
    user: dict = Depends(get_current_user),
):
    result = service.add_wall_comment(user, post_uid, req.text)
    if not result.get("success"):
        code = 404 if result.get("error") == "post_not_found" else 400
        raise HTTPException(status_code=code, detail=result.get("error", "create_failed"))
    return result

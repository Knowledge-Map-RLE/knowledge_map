"""
Layer: Interface Adapters — Web (Routers)
Package: routers.social_network.social
Responsibility: HTTP-контроллеры профилей, друзей, сообществ, трендов, жалоб
и графа социальной сети. Мутации требуют авторизации.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from services.social_network_service import SocialNetworkService
from web.dependencies import get_current_user, get_optional_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["social_network"])

service = SocialNetworkService()


class UpdateProfileRequest(BaseModel):
    bio: Optional[str] = None
    avatar_key: Optional[str] = None
    contacts: Optional[dict] = None


class CreateCommunityRequest(BaseModel):
    name: str
    description: str = ""


class UpdateCommunityRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class CreateComplaintRequest(BaseModel):
    target_type: str
    target_uid: str
    reason: str
    comment: str = ""


# ── Профиль / me ─────────────────────────────────────────────────────────────

@router.get("/social/me")
async def get_me(user: dict = Depends(get_current_user)):
    return service.get_me(user)


@router.put("/social/profile")
async def update_profile(
    req: UpdateProfileRequest,
    user: dict = Depends(get_current_user),
):
    result = service.update_profile(
        user.get("uid", ""),
        bio=req.bio,
        avatar_key=req.avatar_key,
        contacts=req.contacts,
    )
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "user_not_found"))
    return result


# ── Пользователи ─────────────────────────────────────────────────────────────

@router.get("/social/users/search")
async def search_users(q: str = "", limit: int = 20, user: Optional[dict] = Depends(get_optional_user)):
    return {"success": True, "users": service.search_users(q, limit=min(limit, 100))}


@router.get("/social/users/{uid}")
async def get_user(uid: str, user: Optional[dict] = Depends(get_optional_user)):
    profile = service.get_user(uid)
    if profile is None:
        raise HTTPException(status_code=404, detail="user_not_found")
    return {"success": True, "user": profile}


@router.get("/social/users/{uid}/profile")
async def get_user_profile(uid: str, user: Optional[dict] = Depends(get_optional_user)):
    profile = service.get_profile(uid, viewer_uid=(user or {}).get("uid"))
    if profile is None:
        raise HTTPException(status_code=404, detail="user_not_found")
    return {"success": True, "profile": profile}


# ── Друзья ───────────────────────────────────────────────────────────────────

@router.get("/social/friends")
async def list_friends(user: dict = Depends(get_current_user)):
    return {"success": True, "friends": service.list_friends(user.get("uid", ""))}


@router.post("/social/friends/{friend_uid}")
async def add_friend(friend_uid: str, user: dict = Depends(get_current_user)):
    result = service.add_friend(user.get("uid", ""), friend_uid)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "add_friend_failed"))
    return result


@router.delete("/social/friends/{friend_uid}")
async def remove_friend(friend_uid: str, user: dict = Depends(get_current_user)):
    return service.remove_friend(user.get("uid", ""), friend_uid)


# ── Сообщества ───────────────────────────────────────────────────────────────

@router.post("/social/communities")
async def create_community(req: CreateCommunityRequest, user: dict = Depends(get_current_user)):
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="empty_name")
    community = service.create_community(
        owner_uid=user.get("uid", ""), name=name, description=req.description.strip()
    )
    return {"success": True, "community": community}


@router.get("/social/communities")
async def list_communities(limit: int = 100, user: Optional[dict] = Depends(get_optional_user)):
    viewer = (user or {}).get("uid")
    return {
        "success": True,
        "communities": service.list_communities(limit=min(limit, 200), viewer_uid=viewer),
    }


@router.get("/social/communities/search")
async def search_communities(q: str = "", limit: int = 20, user: Optional[dict] = Depends(get_optional_user)):
    viewer = (user or {}).get("uid")
    return {
        "success": True,
        "communities": service.search_communities(q, limit=min(limit, 100), viewer_uid=viewer),
    }


@router.get("/social/communities/mine")
async def my_communities(user: dict = Depends(get_current_user)):
    return {
        "success": True,
        "communities": service.list_owned_communities(user.get("uid", "")),
    }


@router.get("/social/communities/{uid}")
async def get_community(uid: str, user: Optional[dict] = Depends(get_optional_user)):
    community = service.get_community(uid, viewer_uid=(user or {}).get("uid"))
    if community is None:
        raise HTTPException(status_code=404, detail="community_not_found")
    return {"success": True, "community": community}


@router.post("/social/communities/{uid}/join")
async def join_community(uid: str, user: dict = Depends(get_current_user)):
    result = service.join_community(user.get("uid", ""), uid)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "community_not_found"))
    return result


@router.post("/social/communities/{uid}/leave")
async def leave_community(uid: str, user: dict = Depends(get_current_user)):
    return service.leave_community(user.get("uid", ""), uid)


@router.put("/social/communities/{uid}")
async def update_community(
    uid: str,
    req: UpdateCommunityRequest,
    user: dict = Depends(get_current_user),
):
    result = service.update_community(
        user.get("uid", ""), uid, name=req.name, description=req.description
    )
    if not result.get("success"):
        code = 403 if result.get("error") == "forbidden" else 404
        raise HTTPException(status_code=code, detail=result.get("error", "community_not_found"))
    return result


@router.delete("/social/communities/{uid}")
async def delete_community(uid: str, user: dict = Depends(get_current_user)):
    result = service.delete_community(user.get("uid", ""), uid)
    if not result.get("success"):
        code = 403 if result.get("error") == "forbidden" else 404
        raise HTTPException(status_code=code, detail=result.get("error", "community_not_found"))
    return result


# ── Тренды ───────────────────────────────────────────────────────────────────

@router.get("/social/trends")
async def get_trends(limit: int = 10):
    return service.get_trends(limit=min(limit, 50))


# ── Жалобы ───────────────────────────────────────────────────────────────────

@router.post("/social/complaints")
async def create_complaint(req: CreateComplaintRequest, user: dict = Depends(get_current_user)):
    if not req.reason.strip():
        raise HTTPException(status_code=400, detail="empty_reason")
    result = service.create_complaint(
        reporter_uid=user.get("uid", ""),
        target_type=req.target_type,
        target_uid=req.target_uid,
        reason=req.reason.strip(),
        comment=req.comment.strip(),
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "bad_target_type"))
    return result


# ── Граф ─────────────────────────────────────────────────────────────────────

@router.get("/social/graph")
async def get_social_graph(user: Optional[dict] = Depends(get_optional_user)):
    uid = (user or {}).get("uid")
    if uid:
        return service.get_ego_graph(uid)
    return service.get_public_graph()


@router.get("/social/graph/user/{uid}")
async def get_user_graph(uid: str, user: Optional[dict] = Depends(get_optional_user)):
    result = service.get_user_graph(uid, viewer_uid=(user or {}).get("uid"))
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "user_not_found"))
    return result


# ── Изображения ──────────────────────────────────────────────────────────────

@router.post("/social/images")
async def upload_image(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    """Загружает изображение для чата в S3, возвращает object_key."""
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    result = await service.upload_image(
        user.get("uid", ""),
        file.filename or "image",
        file.content_type or "",
        data,
    )
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Upload failed"))
    return result


@router.get("/social/images/{object_key:path}")
async def get_image(object_key: str):
    """Отдаёт содержимое изображения из S3 с корректным content-type."""
    image = await service.get_image(object_key)
    if image is None:
        raise HTTPException(status_code=404, detail="Image not found")
    data, content_type = image
    return Response(content=data, media_type=content_type)


@router.delete("/social/images/{object_key:path}")
async def delete_image(object_key: str, user: dict = Depends(get_current_user)):
    """Удаляет изображение из S3."""
    ok = await service.delete_image(object_key)
    if not ok:
        raise HTTPException(status_code=404, detail="Image not found")
    return {"success": True}


# ── Вклад пользователя / уведомления / resolve ──────────────────────────────

@router.get("/social/users/{uid}/contributions")
async def get_contributions(uid: str, user: Optional[dict] = Depends(get_optional_user)):
    return {"success": True, "contributions": service.get_contributions(uid)}


@router.get("/social/notifications/unread-count")
async def get_unread_count(user: dict = Depends(get_current_user)):
    return {"success": True, "unread_count": service.get_unread_count(user.get("uid", ""))}


@router.get("/social/resolve/{uid}")
async def resolve_entity(uid: str, user: Optional[dict] = Depends(get_optional_user)):
    entity = service.resolve_entity(uid)
    if entity is None:
        raise HTTPException(status_code=404, detail="entity_not_found")
    return {"success": True, "entity": entity}

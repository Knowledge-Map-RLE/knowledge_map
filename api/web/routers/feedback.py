"""
Layer: Frameworks & Drivers — Web
Package: web.routers.feedback
 Responsibility: HTTP-контроллеры системы обратной связи.

Принадлежит слою Web — тонкий контроллер, вызывает use cases / репозиторий
через DI. Не содержит бизнес-логики.

Allowed imports: fastapi, web.dependencies, adapters.repositories.feedback_repository
Forbidden imports: neomodel, domain, services
"""
from __future__ import annotations

import json
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from adapters.repositories.feedback_repository import FeedbackRepository
from domain.models.feedback import FeedbackStatus
from infrastructure.config import settings
from infrastructure.s3.s3_storage import AsyncS3Client
from web.dependencies import (
    get_current_admin,
    get_current_user,
    get_feedback_repository,
    get_s3,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/feedback", tags=["feedback"])

ALLOWED_IMAGE_TYPES = {
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "image/svg+xml",
}
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10 MB


# ── Tickets ────────────────────────────────────────────────────────────────


@router.post("/tickets")
async def create_ticket(
    text: str = Form(""),
    browser_info_json: str = Form("{}"),
    app_version: str = Form(""),
    image_keys_json: str = Form("[]"),
    user: dict = Depends(get_current_user),
    repo: FeedbackRepository = Depends(get_feedback_repository),
):
    """Создать обращение из черновика и первого сообщения."""
    browser_info = {}
    try:
        browser_info = json.loads(browser_info_json)
    except (json.JSONDecodeError, TypeError):
        pass

    ticket = await repo.create_ticket(
        user_uid=user["uid"],
        browser_info=browser_info,
        app_version=app_version,
    )

    image_keys: list[str] = []
    try:
        image_keys = json.loads(image_keys_json)
    except (json.JSONDecodeError, TypeError):
        pass

    if text.strip() or image_keys:
        await repo.add_message(
            ticket_uid=ticket.uid,
            sender_uid=user["uid"],
            sender_type="user",
            text=text.strip(),
            image_s3_keys=image_keys,
        )

    await repo.delete_draft(user["uid"])

    return {
        "success": True,
        "ticket": {
            "uid": ticket.uid,
            "status": ticket.status,
            "created_at": ticket.created_at,
        },
    }


@router.get("/tickets")
async def list_tickets(
    status: Optional[str] = None,
    user_uid: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    user: dict = Depends(get_current_user),
    repo: FeedbackRepository = Depends(get_feedback_repository),
):
    """Список обращений. Админ видит все, обычный пользователь — свои."""
    from web.dependencies import is_admin_user

    is_admin = is_admin_user(user)
    if not is_admin:
        user_uid = user["uid"]

    tickets = await repo.list_tickets(
        user_uid=user_uid,
        status=status,
        limit=limit,
        offset=offset,
    )
    total = await repo.count_tickets(user_uid=user_uid if not is_admin else None, status=status)

    return {
        "tickets": [
            {
                "uid": t.uid,
                "user_uid": t.user_uid,
                "status": t.status,
                "app_version": t.app_version,
                "created_at": t.created_at,
                "updated_at": t.updated_at,
            }
            for t in tickets
        ],
        "total": total,
    }


@router.get("/tickets/{ticket_uid}")
async def get_ticket(
    ticket_uid: str,
    user: dict = Depends(get_current_user),
    repo: FeedbackRepository = Depends(get_feedback_repository),
):
    """Детали обращения (только владелец или админ)."""
    from web.dependencies import is_admin_user

    ticket = await repo.get_ticket(ticket_uid)
    if not ticket:
        raise HTTPException(status_code=404, detail="Обращение не найдено")

    if ticket.user_uid != user["uid"] and not is_admin_user(user):
        raise HTTPException(status_code=403, detail="Нет доступа к этому обращению")

    messages = await repo.get_messages(ticket_uid)

    return {
        "ticket": {
            "uid": ticket.uid,
            "user_uid": ticket.user_uid,
            "status": ticket.status,
            "browser_info": ticket.browser_info,
            "app_version": ticket.app_version,
            "created_at": ticket.created_at,
            "updated_at": ticket.updated_at,
        },
        "messages": [
            {
                "uid": m.uid,
                "sender_uid": m.sender_uid,
                "sender_type": m.sender_type,
                "text": m.text,
                "image_s3_keys": m.image_s3_keys,
                "created_at": m.created_at,
            }
            for m in messages
        ],
    }


@router.patch("/tickets/{ticket_uid}/status")
async def update_ticket_status(
    ticket_uid: str,
    status: str = Form(...),
    user: dict = Depends(get_current_admin),
    repo: FeedbackRepository = Depends(get_feedback_repository),
):
    """Изменить статус обращения (только админ)."""
    valid_statuses = {s.value for s in FeedbackStatus}
    if status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Невалидный статус. Допустимые: {', '.join(sorted(valid_statuses))}",
        )

    ticket = await repo.update_ticket_status(ticket_uid, status)
    return {
        "success": True,
        "ticket": {
            "uid": ticket.uid,
            "status": ticket.status,
            "updated_at": ticket.updated_at,
        },
    }


# ── Messages ───────────────────────────────────────────────────────────────


@router.post("/tickets/{ticket_uid}/messages")
async def send_message(
    ticket_uid: str,
    text: str = Form(""),
    image_keys_json: str = Form("[]"),
    sender_type: str = Form("user"),
    user: dict = Depends(get_current_user),
    repo: FeedbackRepository = Depends(get_feedback_repository),
):
    """Отправить сообщение в обращение.

    sender_type определяет роль, от имени которой пишет пользователь:
    - "user"  — от имени владельца обращения (пользовательский чат);
    - "admin" — от имени поддержки (панель администратора).
    """
    from web.dependencies import is_admin_user

    ticket = await repo.get_ticket(ticket_uid)
    if not ticket:
        raise HTTPException(status_code=404, detail="Обращение не найдено")

    if sender_type not in {"user", "admin"}:
        raise HTTPException(status_code=422, detail="Недопустимый sender_type")

    if sender_type == "admin":
        # Отвечать как поддержка может только админ
        if not is_admin_user(user):
            raise HTTPException(status_code=403, detail="Нет прав администратора")
    else:
        # Писать от имени пользователя может только владелец обращения
        if ticket.user_uid != user["uid"]:
            raise HTTPException(status_code=403, detail="Нет доступа к этому обращению")

    image_keys: list[str] = []
    try:
        image_keys = json.loads(image_keys_json)
    except (json.JSONDecodeError, TypeError):
        pass

    message = await repo.add_message(
        ticket_uid=ticket_uid,
        sender_uid=user["uid"],
        sender_type=sender_type,
        text=text.strip(),
        image_s3_keys=image_keys,
    )

    return {
        "success": True,
        "message": {
            "uid": message.uid,
            "sender_uid": message.sender_uid,
            "sender_type": message.sender_type,
            "text": message.text,
            "image_s3_keys": message.image_s3_keys,
            "created_at": message.created_at,
        },
    }


@router.get("/tickets/{ticket_uid}/messages")
async def get_messages(
    ticket_uid: str,
    limit: int = 100,
    offset: int = 0,
    user: dict = Depends(get_current_user),
    repo: FeedbackRepository = Depends(get_feedback_repository),
):
    """Сообщения обращения (владелец или админ)."""
    from web.dependencies import is_admin_user

    ticket = await repo.get_ticket(ticket_uid)
    if not ticket:
        raise HTTPException(status_code=404, detail="Обращение не найдено")

    if ticket.user_uid != user["uid"] and not is_admin_user(user):
        raise HTTPException(status_code=403, detail="Нет доступа к этому обращению")

    messages = await repo.get_messages(ticket_uid, limit=limit, offset=offset)

    return {
        "messages": [
            {
                "uid": m.uid,
                "sender_uid": m.sender_uid,
                "sender_type": m.sender_type,
                "text": m.text,
                "image_s3_keys": m.image_s3_keys,
                "created_at": m.created_at,
            }
            for m in messages
        ],
    }


# ── Drafts ─────────────────────────────────────────────────────────────────


@router.put("/drafts")
async def save_draft(
    text: str = Form(""),
    user: dict = Depends(get_current_user),
    repo: FeedbackRepository = Depends(get_feedback_repository),
):
    """Сохранить/обновить черновик (upsert)."""
    draft = await repo.upsert_draft(user["uid"], text)
    return {
        "success": True,
        "draft": {
            "text": draft.text,
            "updated_at": draft.updated_at,
        },
    }


@router.get("/drafts")
async def get_draft(
    user: dict = Depends(get_current_user),
    repo: FeedbackRepository = Depends(get_feedback_repository),
):
    """Получить черновик текущего пользователя."""
    draft = await repo.get_draft(user["uid"])
    return {
        "draft": {
            "text": draft.text if draft else "",
            "updated_at": draft.updated_at if draft else 0.0,
        },
    }


@router.delete("/drafts")
async def delete_draft(
    user: dict = Depends(get_current_user),
    repo: FeedbackRepository = Depends(get_feedback_repository),
):
    """Удалить черновик (после отправки обращения)."""
    await repo.delete_draft(user["uid"])
    return {"success": True}


# ── Upload ─────────────────────────────────────────────────────────────────


@router.post("/uploads")
async def upload_image(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
    s3: AsyncS3Client = Depends(get_s3),
):
    """Загрузить изображение обратной связи в S3."""
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Неподдерживаемый тип файла: {file.content_type}",
        )

    contents = await file.read()
    if len(contents) > MAX_IMAGE_SIZE:
        raise HTTPException(status_code=400, detail="Файл слишком большой (макс. 10 МБ)")

    ext = os.path.splitext(file.filename or "upload.png")[1] or ".png"
    from src.uuid8 import uuid8_str
    s3_key = f"feedback/{uuid8_str()}{ext}"

    await s3.upload_bytes(
        contents,
        settings.S3_BUCKET_NAME,
        s3_key,
        content_type=file.content_type,
    )

    return {
        "success": True,
        "s3_key": s3_key,
    }


@router.get("/images/{object_key:path}")
async def get_image(object_key: str, s3: AsyncS3Client = Depends(get_s3)):
    """Отдаёт изображение обратной связи из S3 с корректным content-type."""
    if not object_key.startswith("feedback/"):
        raise HTTPException(status_code=403, detail="Доступ запрещён")

    data = await s3.download_bytes(settings.S3_BUCKET_NAME, object_key)
    if data is None:
        raise HTTPException(status_code=404, detail="Изображение не найдено")

    content_type = "image/png"
    lower = object_key.lower()
    if lower.endswith(".jpg") or lower.endswith(".jpeg"):
        content_type = "image/jpeg"
    elif lower.endswith(".gif"):
        content_type = "image/gif"
    elif lower.endswith(".svg"):
        content_type = "image/svg+xml"
    elif lower.endswith(".webp"):
        content_type = "image/webp"

    return Response(content=data, media_type=content_type)

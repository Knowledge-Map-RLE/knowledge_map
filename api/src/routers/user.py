"""Роутер текущего пользователя: данные, известные api-сервису.

Auth-сервис хранит uid/login/nickname без ролей; роль администратора
эталонов определяется списком ADMIN_UIDS в настройках api.
"""
from typing import Any, Dict

from fastapi import APIRouter, Depends

from web.dependencies import get_current_user, is_admin_user

router = APIRouter(tags=["user"])


@router.get("/user/me")
async def get_me(user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    """Профиль текущего пользователя с ролью (admin/user)."""
    return {
        "success": True,
        "uid": user.get("uid", ""),
        "login": user.get("login", ""),
        "nickname": user.get("nickname", ""),
        "role": "admin" if is_admin_user(user) else "user",
    }

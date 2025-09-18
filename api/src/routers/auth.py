"""Роутер для аутентификации"""
import logging
from typing import Dict, Any

from fastapi import APIRouter, HTTPException

from src.schemas.schemas import (
    UserRegisterRequest, UserLoginRequest, UserRecoveryRequest, 
    UserPasswordResetRequest, User2FASetupRequest, User2FAVerifyRequest,
    AuthResponse, TokenVerifyResponse
)
from services.auth_service import AuthService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])
auth_service = AuthService()


@router.post("/register", response_model=AuthResponse)
async def register_user(request: UserRegisterRequest):
    """Регистрирует нового пользователя"""
    return await auth_service.register_user(request)


@router.post("/login", response_model=AuthResponse)
async def login_user(request: UserLoginRequest):
    """Аутентифицирует пользователя"""
    return await auth_service.login_user(request)


@router.post("/logout")
async def logout_user(token: str, logout_all: bool = False):
    """Выходит из системы"""
    return await auth_service.logout_user(token, logout_all)


@router.post("/verify", response_model=TokenVerifyResponse)
async def verify_user_token(token: str):
    """Проверяет токен пользователя"""
    return await auth_service.verify_user_token(token)


@router.post("/recovery", response_model=AuthResponse)
async def recovery_request(request: UserRecoveryRequest):
    """Проверяет ключ восстановления"""
    return await auth_service.recovery_request(request)


@router.post("/reset-password")
async def reset_password(request: UserPasswordResetRequest):
    """Сбрасывает пароль пользователя"""
    return await auth_service.reset_password(request)


@router.post("/2fa/setup", response_model=AuthResponse)
async def setup_2fa(request: User2FASetupRequest):
    """Настраивает 2FA для пользователя"""
    return await auth_service.setup_2fa(request)


@router.post("/2fa/verify")
async def verify_2fa(request: User2FAVerifyRequest):
    """Проверяет код 2FA"""
    return await auth_service.verify_2fa(request)


@router.get("/captcha")
async def get_captcha():
    """Генерирует капчу (заглушка)"""
    return await auth_service.get_captcha()

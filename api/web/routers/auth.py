"""
Layer: Interface Adapters — Controller (Web)
Package: web.routers.auth
Responsibility: HTTP route handlers для аутентификации. Тонкий контроллер.

Принадлежит слою web. Задачи:
1. Разобрать HTTP-запрос в параметры вызова use case
2. Вызвать use case
3. Вернуть HTTP-ответ

Бизнес-логика здесь отсутствует. Доменные исключения обрабатываются
зарегистрированными обработчиками в web/exception_handlers.py.

Allowed imports: fastapi, application.auth.*, web.dependencies, src.schemas.schemas
Forbidden imports: neomodel, grpc (напрямую), services (напрямую), infrastructure
"""
import logging
from typing import Dict, Any

from fastapi import APIRouter, Depends

from src.schemas.schemas import (
    UserRegisterRequest,
    UserLoginRequest,
    UserRecoveryRequest,
    UserPasswordResetRequest,
    User2FASetupRequest,
    User2FAVerifyRequest,
    AuthResponse,
    TokenVerifyRequest,
    TokenVerifyResponse,
)
from application.auth.register_user import register_user
from application.auth.login_user import login_user
from application.auth.logout_user import logout_user
from application.auth.verify_token import verify_token
from application.auth.manage_2fa import (
    setup_2fa,
    verify_2fa,
    recovery_request,
    reset_password,
)
from web.dependencies import get_auth_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=AuthResponse)
async def register(request: UserRegisterRequest, gateway=Depends(get_auth_client)):
    result = register_user(
        gateway=gateway,
        login=request.login,
        password=request.password,
        nickname=request.nickname,
        captcha=request.captcha,
    )
    return AuthResponse(
        success=True,
        message=result["message"],
        user=result.get("user"),
        recovery_keys=result.get("recovery_keys"),
    )


@router.post("/login", response_model=AuthResponse)
async def login(request: UserLoginRequest, gateway=Depends(get_auth_client)):
    result = login_user(
        gateway=gateway,
        login=request.login,
        password=request.password,
        captcha=request.captcha,
        device_info=request.device_info or "",
        ip_address=request.ip_address or "",
    )
    return AuthResponse(
        success=True,
        message=result["message"],
        token=result.get("token"),
        user=result.get("user"),
        requires_2fa=result.get("requires_2fa"),
    )


@router.post("/logout")
async def logout(token: str, logout_all: bool = False, gateway=Depends(get_auth_client)):
    return logout_user(gateway=gateway, token=token, logout_all=logout_all)


@router.post("/verify", response_model=TokenVerifyResponse)
async def verify(request: TokenVerifyRequest, gateway=Depends(get_auth_client)):
    result = verify_token(gateway=gateway, token=request.token)
    return TokenVerifyResponse(valid=True, message=result["message"], user=result.get("user"))


@router.post("/recovery", response_model=AuthResponse)
async def recovery(request: UserRecoveryRequest, gateway=Depends(get_auth_client)):
    result = recovery_request(
        gateway=gateway,
        recovery_key=request.recovery_key,
        captcha=request.captcha,
    )
    return AuthResponse(
        success=True,
        message=result["message"],
        user={"uid": result.get("user_id")},
    )


@router.post("/reset-password")
async def reset_pwd(request: UserPasswordResetRequest, gateway=Depends(get_auth_client)):
    return reset_password(
        gateway=gateway,
        user_id=request.user_id,
        new_password=request.new_password,
    )


@router.post("/2fa/setup", response_model=AuthResponse)
async def setup_2fa_route(request: User2FASetupRequest, gateway=Depends(get_auth_client)):
    result = setup_2fa(gateway=gateway, user_id=request.user_id)
    return AuthResponse(
        success=True,
        message=result["message"],
        user={"uid": request.user_id},
        recovery_keys=result.get("backup_codes"),
    )


@router.post("/2fa/verify")
async def verify_2fa_route(request: User2FAVerifyRequest, gateway=Depends(get_auth_client)):
    return verify_2fa(gateway=gateway, user_id=request.user_id, code=request.code)


@router.get("/captcha")
async def get_captcha(gateway=Depends(get_auth_client)):
    """Генерирует капчу через auth-микросервис."""
    return gateway.generate_captcha()

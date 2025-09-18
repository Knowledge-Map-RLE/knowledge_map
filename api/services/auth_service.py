"""Сервис для аутентификации"""
import logging
from typing import Dict, Any

from fastapi import HTTPException

from . import auth_client
from src.schemas.schemas import (
    UserRegisterRequest, UserLoginRequest, UserRecoveryRequest, 
    UserPasswordResetRequest, User2FASetupRequest, User2FAVerifyRequest,
    AuthResponse, TokenVerifyResponse
)

logger = logging.getLogger(__name__)


class AuthService:
    """Сервис для аутентификации"""
    
    def __init__(self):
        self.auth_client = auth_client
    
    async def register_user(self, request: UserRegisterRequest) -> AuthResponse:
        """Регистрирует нового пользователя"""
        try:
            result = self.auth_client.register(
                login=request.login,
                password=request.password,
                nickname=request.nickname,
                captcha=request.captcha
            )
            
            if result["success"]:
                return AuthResponse(
                    success=True,
                    message=result["message"],
                    user=result["user"],
                    recovery_keys=result["recovery_keys"]
                )
            else:
                raise HTTPException(status_code=400, detail=result["message"])
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    async def login_user(self, request: UserLoginRequest) -> AuthResponse:
        """Аутентифицирует пользователя"""
        try:
            result = self.auth_client.login(
                login=request.login,
                password=request.password,
                captcha=request.captcha,
                device_info=request.device_info or "",
                ip_address=request.ip_address or ""
            )
            
            if result["success"]:
                return AuthResponse(
                    success=True,
                    message=result["message"],
                    token=result["token"],
                    user=result["user"],
                    requires_2fa=result["requires_2fa"]
                )
            else:
                raise HTTPException(status_code=401, detail=result["message"])
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    async def logout_user(self, token: str, logout_all: bool = False) -> Dict[str, Any]:
        """Выходит из системы"""
        try:
            result = self.auth_client.logout(token, logout_all)
            
            if result["success"]:
                return {"success": True, "message": result["message"]}
            else:
                raise HTTPException(status_code=400, detail=result["message"])
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    async def verify_user_token(self, token: str) -> TokenVerifyResponse:
        """Проверяет токен пользователя"""
        try:
            result = self.auth_client.verify_token(token)
            
            if result["valid"]:
                return TokenVerifyResponse(
                    valid=True,
                    user=result["user"],
                    message=result["message"]
                )
            else:
                raise HTTPException(status_code=401, detail=result["message"])
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    async def recovery_request(self, request: UserRecoveryRequest) -> AuthResponse:
        """Проверяет ключ восстановления"""
        try:
            result = self.auth_client.recovery_request(
                recovery_key=request.recovery_key,
                captcha=request.captcha
            )
            
            if result["success"]:
                return AuthResponse(
                    success=True,
                    message=result["message"],
                    user={"uid": result["user_id"]}
                )
            else:
                raise HTTPException(status_code=400, detail=result["message"])
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    async def reset_password(self, request: UserPasswordResetRequest) -> Dict[str, Any]:
        """Сбрасывает пароль пользователя"""
        try:
            result = self.auth_client.reset_password(
                user_id=request.user_id,
                new_password=request.new_password
            )
            
            if result["success"]:
                return {"success": True, "message": result["message"]}
            else:
                raise HTTPException(status_code=400, detail=result["message"])
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    async def setup_2fa(self, request: User2FASetupRequest) -> AuthResponse:
        """Настраивает 2FA для пользователя"""
        try:
            result = self.auth_client.setup_2fa(request.user_id)
            
            if result["success"]:
                return AuthResponse(
                    success=True,
                    message=result["message"],
                    user={"uid": request.user_id},
                    recovery_keys=result["backup_codes"]
                )
            else:
                raise HTTPException(status_code=400, detail=result["message"])
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    async def verify_2fa(self, request: User2FAVerifyRequest) -> Dict[str, Any]:
        """Проверяет код 2FA"""
        try:
            result = self.auth_client.verify_2fa(
                user_id=request.user_id,
                code=request.code
            )
            
            if result["success"]:
                return {"success": True, "message": result["message"]}
            else:
                raise HTTPException(status_code=400, detail=result["message"])
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    async def get_captcha(self) -> Dict[str, str]:
        """Генерирует капчу (заглушка)"""
        # В реальной реализации здесь будет генерация капчи
        return {
            "captcha_id": "test_captcha_123",
            "captcha_image": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
        }

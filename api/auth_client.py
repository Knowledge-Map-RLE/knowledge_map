import grpc
import auth_pb2
import auth_pb2_grpc
from typing import Optional, Dict, Any
from config import settings


class AuthClient:
    def __init__(self):
        self.channel = grpc.insecure_channel(f"{settings.AUTH_SERVICE_HOST}:{settings.AUTH_SERVICE_PORT}")
        self.stub = auth_pb2_grpc.AuthServiceStub(self.channel)
    
    def register(self, login: str, password: str, nickname: str, captcha: str) -> Dict[str, Any]:
        """Регистрирует нового пользователя"""
        request = auth_pb2.RegisterRequest(
            login=login,
            password=password,
            nickname=nickname,
            captcha=captcha
        )
        
        try:
            response = self.stub.Register(request)
            return {
                "success": response.success,
                "message": response.message,
                "user": {
                    "uid": response.user.uid,
                    "login": response.user.login,
                    "nickname": response.user.nickname,
                    "is_active": response.user.is_active,
                    "is_2fa_enabled": response.user.is_2fa_enabled
                } if response.user else None,
                "recovery_keys": list(response.recovery_keys)
            }
        except grpc.RpcError as e:
            return {
                "success": False,
                "message": f"Ошибка связи с сервисом авторизации: {e.details()}"
            }
    
    def login(self, login: str, password: str, captcha: str, device_info: str = "", ip_address: str = "") -> Dict[str, Any]:
        """Аутентифицирует пользователя"""
        request = auth_pb2.LoginRequest(
            login=login,
            password=password,
            captcha=captcha,
            device_info=device_info,
            ip_address=ip_address
        )
        
        try:
            response = self.stub.Login(request)
            return {
                "success": response.success,
                "message": response.message,
                "token": response.token,
                "user": {
                    "uid": response.user.uid,
                    "login": response.user.login,
                    "nickname": response.user.nickname,
                    "is_active": response.user.is_active,
                    "is_2fa_enabled": response.user.is_2fa_enabled
                } if response.user else None,
                "requires_2fa": response.requires_2fa
            }
        except grpc.RpcError as e:
            return {
                "success": False,
                "message": f"Ошибка связи с сервисом авторизации: {e.details()}"
            }
    
    def verify_token(self, token: str) -> Dict[str, Any]:
        """Проверяет токен"""
        request = auth_pb2.VerifyTokenRequest(token=token)
        
        try:
            response = self.stub.VerifyToken(request)
            return {
                "valid": response.valid,
                "user": {
                    "uid": response.user.uid,
                    "login": response.user.login,
                    "nickname": response.user.nickname,
                    "is_active": response.user.is_active,
                    "is_2fa_enabled": response.user.is_2fa_enabled
                } if response.user else None,
                "message": response.message
            }
        except grpc.RpcError as e:
            return {
                "valid": False,
                "message": f"Ошибка связи с сервисом авторизации: {e.details()}"
            }
    
    def logout(self, token: str, logout_all: bool = False) -> Dict[str, Any]:
        """Выходит из системы"""
        request = auth_pb2.LogoutRequest(token=token, logout_all=logout_all)
        
        try:
            response = self.stub.Logout(request)
            return {
                "success": response.success,
                "message": response.message
            }
        except grpc.RpcError as e:
            return {
                "success": False,
                "message": f"Ошибка связи с сервисом авторизации: {e.details()}"
            }
    
    def recovery_request(self, recovery_key: str, captcha: str) -> Dict[str, Any]:
        """Проверяет ключ восстановления"""
        request = auth_pb2.RecoveryRequest(
            recovery_key=recovery_key,
            captcha=captcha
        )
        
        try:
            response = self.stub.RecoveryRequest(request)
            return {
                "success": response.success,
                "message": response.message,
                "user_id": response.user_id
            }
        except grpc.RpcError as e:
            return {
                "success": False,
                "message": f"Ошибка связи с сервисом авторизации: {e.details()}"
            }
    
    def reset_password(self, user_id: str, new_password: str) -> Dict[str, Any]:
        """Сбрасывает пароль"""
        request = auth_pb2.ResetPasswordRequest(
            user_id=user_id,
            new_password=new_password
        )
        
        try:
            response = self.stub.ResetPassword(request)
            return {
                "success": response.success,
                "message": response.message
            }
        except grpc.RpcError as e:
            return {
                "success": False,
                "message": f"Ошибка связи с сервисом авторизации: {e.details()}"
            }
    
    def setup_2fa(self, user_id: str) -> Dict[str, Any]:
        """Настраивает 2FA"""
        request = auth_pb2.Setup2FARequest(user_id=user_id)
        
        try:
            response = self.stub.Setup2FA(request)
            return {
                "success": response.success,
                "secret": response.secret,
                "qr_code": response.qr_code,
                "backup_codes": list(response.backup_codes),
                "message": response.message
            }
        except grpc.RpcError as e:
            return {
                "success": False,
                "message": f"Ошибка связи с сервисом авторизации: {e.details()}"
            }
    
    def verify_2fa(self, user_id: str, code: str) -> Dict[str, Any]:
        """Проверяет код 2FA"""
        request = auth_pb2.Verify2FARequest(user_id=user_id, code=code)
        
        try:
            response = self.stub.Verify2FA(request)
            return {
                "success": response.success,
                "message": response.message
            }
        except grpc.RpcError as e:
            return {
                "success": False,
                "message": f"Ошибка связи с сервисом авторизации: {e.details()}"
            }
    
    def __del__(self):
        if hasattr(self, 'channel'):
            self.channel.close()


# Глобальный экземпляр клиента
auth_client = AuthClient() 
"""
Layer: Frameworks & Drivers — Infrastructure
Package: infrastructure.auth_grpc_client
Responsibility: gRPC-клиент микросервиса аутентификации (проверка токена).

Принадлежит слою Infrastructure. Использует сгенерированные протобуферы
из utils/generated (см. start.ps1).
"""
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import grpc

from config import settings

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "utils"))
sys.path.insert(0, str(_PROJECT_ROOT / "utils" / "generated"))

from generated import auth_pb2, auth_pb2_grpc  # noqa: E402


class AuthClient:
    def __init__(self, host: str = settings.AUTH_SERVICE_HOST, port: int = settings.AUTH_SERVICE_PORT):
        self._channel = grpc.insecure_channel(f"{host}:{port}")
        self._stub = auth_pb2_grpc.AuthServiceStub(self._channel)

    def verify_token(self, token: str) -> Dict[str, Any]:
        request = auth_pb2.VerifyTokenRequest(token=token)
        try:
            response = self._stub.VerifyToken(request)
        except grpc.RpcError as exc:
            return {
                "valid": False,
                "user": None,
                "message": f"Ошибка связи с сервисом авторизации: {exc.details()}",
            }
        return {
            "valid": response.valid,
            "user": {
                "uid": response.user.uid,
                "login": response.user.login,
                "nickname": response.user.nickname,
                "is_active": response.user.is_active,
                "is_2fa_enabled": response.user.is_2fa_enabled,
            } if response.user else None,
            "message": response.message,
        }

    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        request = auth_pb2.GetUserRequest(user_id=user_id)
        try:
            response = self._stub.GetUser(request)
        except grpc.RpcError:
            return None
        if not response.success or not response.user:
            return None
        return {
            "uid": response.user.uid,
            "login": response.user.login,
            "nickname": response.user.nickname,
        }

    def close(self) -> None:
        try:
            self._channel.close()
        except Exception:
            pass


auth_client = AuthClient()

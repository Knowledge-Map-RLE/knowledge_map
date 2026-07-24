"""
Layer: Application (Use Cases) — Ports
Package: application.ports.auth_gateway
Responsibility: Контракт сервиса аутентификации.

Реализация находится в infrastructure/grpc_clients/auth_grpc_client.py.

Allowed imports: typing, стандартная библиотека
Forbidden imports: grpc, fastapi, neomodel
"""
from __future__ import annotations

from typing import Protocol, Dict, Any


class AuthGatewayProtocol(Protocol):
    """Интерфейс микросервиса аутентификации."""

    def register(
        self, login: str, password: str, nickname: str, captcha: str
    ) -> Dict[str, Any]: ...

    def login(
        self,
        login: str,
        password: str,
        captcha: str,
        device_info: str = "",
        ip_address: str = "",
    ) -> Dict[str, Any]: ...

    def verify_token(self, token: str) -> Dict[str, Any]: ...

    def logout(self, token: str, logout_all: bool = False) -> Dict[str, Any]: ...

    def recovery_request(self, recovery_key: str, captcha: str) -> Dict[str, Any]: ...

    def reset_password(self, user_id: str, new_password: str) -> Dict[str, Any]: ...

    def setup_2fa(self, user_id: str) -> Dict[str, Any]: ...

    def verify_2fa(self, user_id: str, code: str) -> Dict[str, Any]: ...

    def get_user_by_id(self, user_id: str) -> Dict[str, Any]: ...

    def list_users(self) -> Dict[str, Any]: ...

    def generate_captcha(self) -> Dict[str, Any]: ...

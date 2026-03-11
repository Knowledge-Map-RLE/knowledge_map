"""
Layer: Application (Use Cases)
Package: application.auth.logout_user
Responsibility: Оркестрирует выход пользователя из системы.

Allowed imports: domain.exceptions, application.ports.auth_gateway
Forbidden imports: fastapi, neomodel, infrastructure, web
"""
from __future__ import annotations

from typing import Dict, Any

from domain.exceptions import ExternalServiceError
from application.ports.auth_gateway import AuthGatewayProtocol


def logout_user(
    gateway: AuthGatewayProtocol,
    token: str,
    logout_all: bool = False,
) -> Dict[str, Any]:
    result = gateway.logout(token=token, logout_all=logout_all)
    if not result.get("success"):
        message = result.get("message", "")
        if "Ошибка связи" in message:
            raise ExternalServiceError("auth", message)
    return result

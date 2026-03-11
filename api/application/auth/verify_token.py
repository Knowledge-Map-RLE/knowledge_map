"""
Layer: Application (Use Cases)
Package: application.auth.verify_token
Responsibility: Проверяет действительность токена пользователя.

Allowed imports: domain.exceptions, application.ports.auth_gateway
Forbidden imports: fastapi, neomodel, infrastructure, web
"""
from __future__ import annotations

from typing import Dict, Any

from domain.exceptions import AuthenticationFailed, ExternalServiceError
from application.ports.auth_gateway import AuthGatewayProtocol


def verify_token(gateway: AuthGatewayProtocol, token: str) -> Dict[str, Any]:
    result = gateway.verify_token(token=token)
    if not result.get("valid"):
        message = result.get("message", "Токен недействителен")
        if "Ошибка связи" in message:
            raise ExternalServiceError("auth", message)
        raise AuthenticationFailed(message)
    return result

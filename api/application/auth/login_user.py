"""
Layer: Application (Use Cases)
Package: application.auth.login_user
Responsibility: Оркестрирует аутентификацию пользователя.

Allowed imports: domain.exceptions, application.ports.auth_gateway, стандартная библиотека
Forbidden imports: fastapi, neomodel, grpc, infrastructure, adapters, web
"""
from __future__ import annotations

import json
from typing import Dict, Any

from domain.exceptions import AuthenticationFailed, ExternalServiceError
from application.ports.auth_gateway import AuthGatewayProtocol


def login_user(
    gateway: AuthGatewayProtocol,
    login: str,
    password: str,
    captcha: str,
    device_info: str = "",
    ip_address: str = "",
    remember_me: bool = False,
) -> Dict[str, Any]:
    """
    Аутентифицирует пользователя.

    Raises:
        AuthenticationFailed: неверные учётные данные
        ExternalServiceError: ошибка связи с Auth-сервисом
    """
    if remember_me:
        try:
            payload = json.loads(device_info) if device_info else {}
        except (ValueError, TypeError):
            payload = {}
        payload["remember_me"] = True
        device_info = json.dumps(payload)

    result = gateway.login(
        login=login,
        password=password,
        captcha=captcha,
        device_info=device_info,
        ip_address=ip_address,
    )

    if not result.get("success"):
        message = result.get("message", "Ошибка аутентификации")
        if "Ошибка связи" in message:
            raise ExternalServiceError("auth", message)
        raise AuthenticationFailed(message)

    return result

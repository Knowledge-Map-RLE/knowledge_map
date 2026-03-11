"""
Layer: Application (Use Cases)
Package: application.auth.manage_2fa
Responsibility: Настройка и проверка двухфакторной аутентификации.

Allowed imports: domain.exceptions, application.ports.auth_gateway
Forbidden imports: fastapi, neomodel, infrastructure, web
"""
from __future__ import annotations

from typing import Dict, Any

from domain.exceptions import AuthenticationFailed, ExternalServiceError
from application.ports.auth_gateway import AuthGatewayProtocol


def setup_2fa(gateway: AuthGatewayProtocol, user_id: str) -> Dict[str, Any]:
    result = gateway.setup_2fa(user_id=user_id)
    if not result.get("success"):
        message = result.get("message", "Ошибка настройки 2FA")
        if "Ошибка связи" in message:
            raise ExternalServiceError("auth", message)
        raise AuthenticationFailed(message)
    return result


def verify_2fa(gateway: AuthGatewayProtocol, user_id: str, code: str) -> Dict[str, Any]:
    result = gateway.verify_2fa(user_id=user_id, code=code)
    if not result.get("success"):
        message = result.get("message", "Неверный код 2FA")
        if "Ошибка связи" in message:
            raise ExternalServiceError("auth", message)
        raise AuthenticationFailed(message)
    return result


def recovery_request(
    gateway: AuthGatewayProtocol, recovery_key: str, captcha: str
) -> Dict[str, Any]:
    result = gateway.recovery_request(recovery_key=recovery_key, captcha=captcha)
    if not result.get("success"):
        message = result.get("message", "Неверный ключ восстановления")
        if "Ошибка связи" in message:
            raise ExternalServiceError("auth", message)
        raise AuthenticationFailed(message)
    return result


def reset_password(
    gateway: AuthGatewayProtocol, user_id: str, new_password: str
) -> Dict[str, Any]:
    result = gateway.reset_password(user_id=user_id, new_password=new_password)
    if not result.get("success"):
        message = result.get("message", "Ошибка смены пароля")
        if "Ошибка связи" in message:
            raise ExternalServiceError("auth", message)
        raise AuthenticationFailed(message)
    return result

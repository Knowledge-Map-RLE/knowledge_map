"""
Layer: Application (Use Cases)
Package: application.auth.register_user
Responsibility: Оркестрирует регистрацию нового пользователя.

Принадлежит слою Application, потому что содержит логику приложения — проверяет
результат gRPC-ответа и бросает доменные исключения. Не знает о HTTP.

Allowed imports: domain.exceptions, application.ports.auth_gateway, стандартная библиотека
Forbidden imports: fastapi, neomodel, grpc (напрямую), infrastructure, adapters, web
"""
from __future__ import annotations

from typing import Dict, Any

from domain.exceptions import RegistrationFailed, ExternalServiceError
from application.ports.auth_gateway import AuthGatewayProtocol


def register_user(
    gateway: AuthGatewayProtocol,
    login: str,
    password: str,
    nickname: str,
    captcha: str,
) -> Dict[str, Any]:
    """
    Регистрирует нового пользователя через Auth-микросервис.

    Returns:
        dict с ключами: success, message, user, recovery_keys

    Raises:
        RegistrationFailed: если микросервис вернул ошибку
        ExternalServiceError: если связь с микросервисом прервана
    """
    result = gateway.register(login=login, password=password, nickname=nickname, captcha=captcha)

    if not result.get("success"):
        message = result.get("message", "Ошибка регистрации")
        if "Ошибка связи" in message:
            raise ExternalServiceError("auth", message)
        raise RegistrationFailed(message)

    return result

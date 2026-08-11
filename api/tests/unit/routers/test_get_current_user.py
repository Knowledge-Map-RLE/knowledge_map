"""Тесты FastAPI-зависимости get_current_user (гейтинг write/AI эндпоинтов).

Сценарии:
  1. Отсутствует Bearer-токен -> AuthenticationFailed (401).
  2. Невалидный токен -> AuthenticationFailed (401).
  3. Сервис авторизации недоступен -> ExternalServiceError (502).
  4. Валидный токен -> возвращается dict пользователя.
  5. Интеграция: gated-эндпоинт без токена возвращает 401 JSON.
"""

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from domain.exceptions import AuthenticationFailed, ExternalServiceError
from web import dependencies
from web.exception_handlers import register_exception_handlers


class FakeAuthClient:
    def __init__(self, result):
        self._result = result

    def verify_token(self, token):
        return self._result


class Creds:
    def __init__(self, credentials):
        self.credentials = credentials


def test_missing_bearer_token_raises_authentication_failed():
    with pytest.raises(AuthenticationFailed):
        dependencies.get_current_user(credentials=None)


def test_empty_credentials_raises_authentication_failed():
    with pytest.raises(AuthenticationFailed):
        dependencies.get_current_user(credentials=Creds(""))


def test_invalid_token_raises_authentication_failed(monkeypatch):
    fake = FakeAuthClient(
        {"valid": False, "user": None, "message": "Токен недействителен"}
    )
    monkeypatch.setattr(dependencies, "auth_client", fake)
    with pytest.raises(AuthenticationFailed):
        dependencies.get_current_user(credentials=Creds("bad-token"))


def test_auth_service_unreachable_raises_external_service_error(monkeypatch):
    fake = FakeAuthClient(
        {
            "valid": False,
            "user": None,
            "message": "Ошибка связи с сервисом авторизации: deadline exceeded",
        }
    )
    monkeypatch.setattr(dependencies, "auth_client", fake)
    with pytest.raises(ExternalServiceError):
        dependencies.get_current_user(credentials=Creds("token"))


def test_valid_token_returns_user(monkeypatch):
    user = {"uid": "u1", "login": "bob", "nickname": "Bob"}
    fake = FakeAuthClient({"valid": True, "user": user, "message": ""})
    monkeypatch.setattr(dependencies, "auth_client", fake)
    result = dependencies.get_current_user(credentials=Creds("good-token"))
    assert result == user


def _build_gated_app():
    app = FastAPI()

    @app.put("/write")
    async def write_endpoint(user: dict = Depends(dependencies.get_current_user)):
        return {"ok": True, "user": user["uid"]}

    register_exception_handlers(app)
    return app


def test_gated_endpoint_returns_401_without_token():
    client = TestClient(_build_gated_app())
    resp = client.put("/write")
    assert resp.status_code == 401
    assert "detail" in resp.json()


def test_gated_endpoint_returns_401_with_invalid_token(monkeypatch):
    fake = FakeAuthClient(
        {"valid": False, "user": None, "message": "Токен недействителен"}
    )
    monkeypatch.setattr(dependencies, "auth_client", fake)
    client = TestClient(_build_gated_app())
    resp = client.put("/write", headers={"Authorization": "Bearer bad-token"})
    assert resp.status_code == 401


def test_gated_endpoint_returns_200_with_valid_token(monkeypatch):
    user = {"uid": "u1", "login": "bob", "nickname": "Bob"}
    fake = FakeAuthClient({"valid": True, "user": user, "message": ""})
    monkeypatch.setattr(dependencies, "auth_client", fake)
    client = TestClient(_build_gated_app())
    resp = client.put("/write", headers={"Authorization": "Bearer good-token"})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "user": "u1"}

"""
Layer: Interface Adapters — Web
Package: web.dependencies
Responsibility: FastAPI Depends() — DI-wiring, связывает Protocol с реализациями.

Принадлежит слою web. Создаёт конкретные реализации и передаёт их в use cases
через FastAPI dependency injection. Это ЕДИНСТВЕННОЕ место, где use cases
узнают о конкретных реализациях.

Allowed imports: fastapi, adapters.repositories.*, infrastructure.*, application.*
Forbidden imports: neomodel (напрямую)
"""
from typing import Optional

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from adapters.repositories.block_repository import BlockRepository
from adapters.repositories.link_repository import LinkRepository
from adapters.repositories.document_repository import DocumentRepository
from adapters.repositories.annotation_repository import AnnotationRepository
from adapters.repositories.action_repository import ActionRepository
from adapters.repositories.linguistic_pattern_repository import LinguisticPatternRepository
from adapters.repositories.pattern_graph_repository import PatternGraphRepository
from infrastructure.s3.s3_storage import get_s3_client, AsyncS3Client
from infrastructure.grpc_clients.auth_grpc_client import auth_client, AuthClient
from infrastructure.config import settings

from application.auth.verify_token import verify_token
from domain.exceptions import AuthenticationFailed, ExternalServiceError


# ── Репозитории ────────────────────────────────────────────────────────────────

def get_block_repository() -> BlockRepository:
    return BlockRepository()


def get_link_repository() -> LinkRepository:
    return LinkRepository()


def get_document_repository() -> DocumentRepository:
    return DocumentRepository()


def get_annotation_repository() -> AnnotationRepository:
    return AnnotationRepository()





def get_action_repository() -> ActionRepository:
    return ActionRepository()


def get_linguistic_pattern_repository() -> LinguisticPatternRepository:
    return LinguisticPatternRepository()


def get_pattern_graph_repository() -> PatternGraphRepository:
    return PatternGraphRepository()


# ── Инфраструктурные сервисы ───────────────────────────────────────────────────

def get_s3() -> AsyncS3Client:
    return get_s3_client()


def get_auth_client() -> AuthClient:
    return auth_client


# ── Layout клиент ──────────────────────────────────────────────────────────────

def get_layout_client_dep():
    from services import get_layout_client  # TRANSITIONAL import
    return get_layout_client()


# ── NLP клиент ────────────────────────────────────────────────────────────────

def get_nlp_client_dep():
    from services.nlp_grpc_client import get_nlp_grpc_client
    return get_nlp_grpc_client()


# ── Авторизация ─────────────────────────────────────────────────────────────────

_bearer_scheme = HTTPBearer(auto_error=False, description="Bearer-токен пользователя")


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> dict:
    """FastAPI-зависимость: текущий пользователь из Bearer-токена.

    Бросает AuthenticationFailed (401) при отсутствии/невалидности токена,
    ExternalServiceError (502) — если сервис авторизации недоступен.
    Обработчики исключений зарегистрированы в web/exception_handlers.py.
    """
    if credentials is None or not credentials.credentials:
        raise AuthenticationFailed("Не авторизован: отсутствует Bearer-токен")
    result = verify_token(auth_client, credentials.credentials)
    user = result.get("user")
    if not user:
        raise AuthenticationFailed("Токен недействителен")
    return user


def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> Optional[dict]:
    """FastAPI-зависимость: текущий пользователь из Bearer-токена либо None.

    Для публичных read-only эндпоинтов (профили, сообщества, граф), которые
    должны работать и без регистрации: если токен отсутствует или невалиден —
    возвращается None вместо исключения.
    """
    if credentials is None or not credentials.credentials:
        return None
    try:
        result = verify_token(auth_client, credentials.credentials)
    except (AuthenticationFailed, ExternalServiceError):
        return None
    user = result.get("user")
    return user or None

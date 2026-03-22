"""
Layer: Interface Adapters — Web
Package: web.dependencies
Responsibility: FastAPI Depends() — DI-wiring, связывает Protocol с реализациями.

Принадлежит слою web. Создаёт конкретные реализации и передаёт их в use cases
через FastAPI dependency injection. Это ЕДИНСТВЕННОЕ место, где use cases
узнают о конкретных реализациях.

Allowed imports: fastapi, adapters.repositories.*, infrastructure.*, application.ports.*
Forbidden imports: neomodel (напрямую), domain (только через порты)
"""
from fastapi import Depends

from adapters.repositories.block_repository import BlockRepository
from adapters.repositories.link_repository import LinkRepository
from adapters.repositories.document_repository import DocumentRepository
from adapters.repositories.annotation_repository import AnnotationRepository
from adapters.repositories.user_repository import UserRepository
from adapters.repositories.linguistic_pattern_repository import LinguisticPatternRepository
from infrastructure.s3.s3_storage import get_s3_client, AsyncS3Client
from infrastructure.grpc_clients.auth_grpc_client import auth_client, AuthClient
from infrastructure.config import settings


# ── Репозитории ────────────────────────────────────────────────────────────────

def get_block_repository() -> BlockRepository:
    return BlockRepository()


def get_link_repository() -> LinkRepository:
    return LinkRepository()


def get_document_repository() -> DocumentRepository:
    return DocumentRepository()


def get_annotation_repository() -> AnnotationRepository:
    return AnnotationRepository()


def get_user_repository() -> UserRepository:
    return UserRepository()


def get_linguistic_pattern_repository() -> LinguisticPatternRepository:
    return LinguisticPatternRepository()


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

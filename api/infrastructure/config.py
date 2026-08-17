"""
Layer: Frameworks & Drivers — Infrastructure
Package: infrastructure.config
Responsibility: Централизованное управление конфигурацией через переменные окружения.

Принадлежит слою Infrastructure, потому что использует pydantic-settings для
чтения конфигурации из окружения — детали развёртывания.

Перемещено из services/config.py.

Allowed imports: pydantic-settings, os, стандартная библиотека
Forbidden imports: fastapi, neomodel, grpc, aioboto3, application, domain, adapters, web
"""
import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env.local" if os.path.exists(
            os.path.join(os.path.dirname(__file__), "..", ".env.local")
        ) else ".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",  # Игнорируем неизвестные переменные окружения
    )

    # База данных
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "password"

    # Layout сервис
    LAYOUT_SERVICE_HOST: str = "localhost"
    LAYOUT_SERVICE_PORT: int = 50051

    # Auth сервис
    AUTH_SERVICE_HOST: str = "localhost"
    AUTH_SERVICE_PORT: int = 50057

    # Billing сервис
    BILLING_SERVICE_URL: str = "http://localhost:50058"

    # Внутренний токен для межсервисных вызовов api -> billing
    INTERNAL_TOKEN: str = ""

    # PDF to Markdown сервис
    PDF_TO_MD_SERVICE_URL: str = "http://localhost:8002"

    # S3
    S3_ENDPOINT_URL: str = "http://localhost:9000"
    S3_ACCESS_KEY: str = "minio"
    S3_SECRET_KEY: str = "minio123456"
    S3_REGION: str = "us-east-1"
    S3_BUCKET_NAME: str = "knowledge-map-data"

    # API
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    # LLM Extraction (triplet extraction from articles)
    LLM_EXTRACT_MODEL: str = "qwen/qwen3-4b"
    LLM_MAX_CHUNK_CHARS: int = 7000
    LLM_MAX_TOKENS: int = 20000
    LLM_TIMEOUT: int = 900
    LLM_TEMPERATURE: float = 0.2
    LLM_MAX_RETRIES: int = 2
    LLM_SEQ_REF_RATIO: float = 0.7788
    LLM_UUIDREF_MAX_WORDS: int = 1
    LLM_UUIDREF_MIN_FREQ: int = 3

    # Debug режим
    DEBUG: bool = False

    def get_database_url(self) -> str:
        """Формирует DATABASE_URL для neomodel."""
        uri = self.NEO4J_URI
        for scheme in ("bolt+s", "neo4j+s", "neo4j", "bolt"):
            prefix = f"{scheme}://"
            if uri.startswith(prefix):
                hostport = uri[len(prefix):]
                return f"{scheme}://{self.NEO4J_USER}:{self.NEO4J_PASSWORD}@{hostport}"
        return uri


settings = Settings()

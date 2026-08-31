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
from pathlib import Path
from typing import List, Optional
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
    LLM_EXTRACT_MODEL: str = "gpt://b1gulkghbtm74u59sakh/deepseek-v4-flash/latest"
    LLM_MAX_CHUNK_CHARS: int = 3500
    LLM_MAX_TOKENS: int = 80000
    LLM_TIMEOUT: int = 1800
    LLM_TEMPERATURE: float = 0.1
    LLM_MAX_RETRIES: int = 2
    LLM_SEQ_REF_RATIO: float = 0.7788
    LLM_UUIDREF_MAX_WORDS: int = 1
    LLM_UUIDREF_MIN_FREQ: int = 3
    LLM_WHOLE_ARTICLE_MAX_CHARS: int = 100000

    # Золотые эталоны LLM-экстракции (eval/gold)
    # Каталог золотых эталонов (eval/gold).
    # Пусто -> eval/gold в корне репозитория. Относительный путь
    # отсчитывается от корня репозитория (не от рабочей директории процесса);
    # в production обычно абсолютный путь к примонтированному тому.
    GOLD_DIR: str = ""

    # Администраторы эталонов: uid через запятую.
    # Временная схема до появления ролей в auth-сервисе; проверка —
    # единственная точка web.dependencies.get_current_admin.
    ADMIN_UIDS: str = ""

    # Debug режим
    DEBUG: bool = False

    @property
    def admin_uids(self) -> List[str]:
        return [uid.strip() for uid in self.ADMIN_UIDS.split(",") if uid.strip()]

    @property
    def resolved_gold_dir(self) -> Path:
        """Каталог эталонов: относительные пути — от корня репозитория."""
        repo_root = Path(__file__).resolve().parents[2]
        if not self.GOLD_DIR:
            return repo_root / "eval" / "gold"
        path = Path(self.GOLD_DIR)
        if not path.is_absolute():
            path = repo_root / path
        return path.resolve()

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

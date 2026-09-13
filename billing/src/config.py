"""
Layer: Frameworks & Drivers — Infrastructure
Package: config
Responsibility: Настройки микросервиса billing (env + .env).
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


def _resolve_env_file() -> str:
    """Выбор env-файла по ENVIRONMENT: `.env.<ENV>` > `.env.local` > `.env`."""
    import os
    from pathlib import Path

    base_dir = Path(__file__).resolve().parents[1]  # каталог сервиса billing/
    env = os.environ.get("ENVIRONMENT", "development")
    for name in (f".env.{env}", ".env.local", ".env"):
        candidate = base_dir / name
        if candidate.is_file():
            return str(candidate)
    return ""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_resolve_env_file(), extra="ignore")

    ENVIRONMENT: str = "development"

    BILLING_HOST: str = "0.0.0.0"
    BILLING_PORT: int = 50058
    LOG_LEVEL: str = "INFO"

    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "password"

    AUTH_SERVICE_HOST: str = "localhost"
    AUTH_SERVICE_PORT: int = 50057

    YOOKASSA_SHOP_ID: str = ""
    YOOKASSA_SECRET_KEY: str = ""
    YOOKASSA_API_URL: str = "https://api.yookassa.ru/v3"
    YOOKASSA_RETURN_URL: str = "http://localhost:5555/subscription"

    # Сервис-ту-сервис доступ (заголовок X-Internal-Token) — для main API
    INTERNAL_TOKEN: str = ""

    RECONCILIATION_INTERVAL_SECONDS: int = 300

    def get_database_url(self) -> str:
        host = self.NEO4J_URI
        for scheme in ("bolt+s://", "neo4j+s://", "bolt://", "neo4j://"):
            if host.startswith(scheme):
                host = host[len(scheme):]
                break
        return f"bolt://{self.NEO4J_USER}:{self.NEO4J_PASSWORD}@{host}"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

"""
Layer: Frameworks & Drivers — Infrastructure
Package: config
Responsibility: Настройки микросервиса billing (env + .env).
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

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

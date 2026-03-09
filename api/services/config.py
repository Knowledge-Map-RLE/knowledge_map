import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env.local" if os.path.exists(os.path.join(os.path.dirname(__file__), "..", "..", ".env.local")) else ".env",
        env_file_encoding="utf-8",
        case_sensitive=True
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
    AUTH_SERVICE_PORT: int = 50051

    # PDF to Markdown сервис
    PDF_TO_MD_SERVICE_URL: str = "http://localhost:8002"
    
    # S3
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_REGION: str = "us-east-1"
    S3_BUCKET_NAME: str = "knowledge-map-data"
    
    # API
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    
    # Debug режим
    DEBUG: bool = False
    
    
    def get_database_url(self) -> str:
        # neomodel ожидает формат: scheme://user:password@host:port
        # Поддерживаем bolt://, neo4j://, bolt+s://, neo4j+s:// (AuraDB)
        uri = self.NEO4J_URI
        for scheme in ("bolt+s", "neo4j+s", "neo4j", "bolt"):
            prefix = f"{scheme}://"
            if uri.startswith(prefix):
                hostport = uri[len(prefix):]
                return f"{scheme}://{self.NEO4J_USER}:{self.NEO4J_PASSWORD}@{hostport}"
        return uri


settings = Settings()
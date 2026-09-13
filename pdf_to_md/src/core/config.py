"""Configuration settings for PDF to Markdown service"""

import os
from pathlib import Path
from typing import Optional
from pydantic import Field, ConfigDict
from pydantic_settings import BaseSettings


def _resolve_env_file() -> str:
    """Выбор env-файла по ENVIRONMENT: `.env.<ENV>` > `.env.local` > `.env`."""
    base_dir = Path(__file__).resolve().parents[2]  # каталог сервиса pdf_to_md/
    env = os.environ.get("ENVIRONMENT", "development")
    for name in (f".env.{env}", ".env.local", ".env"):
        candidate = base_dir / name
        if candidate.is_file():
            return str(candidate)
    return ""


class Settings(BaseSettings):
    """Application settings"""
    
    # Service settings
    service_name: str = Field(default="pdf-to-md-service", env="SERVICE_NAME")
    version: str = Field(default="0.1.0", env="SERVICE_VERSION")
    debug: bool = Field(default=False, env="DEBUG")
    environment: str = Field(default="development", env="ENVIRONMENT")
    
    # API settings
    api_host: str = Field(default="0.0.0.0", env="API_HOST")
    api_port: int = Field(default=8002, env="API_PORT")
    grpc_port: int = Field(default=50053, env="GRPC_PORT")
    
    # File processing settings
    max_file_size_mb: int = Field(default=100, env="MAX_FILE_SIZE_MB")
    max_concurrent_conversions: int = Field(default=5, env="MAX_CONCURRENT_CONVERSIONS")
    conversion_timeout_seconds: int = Field(default=1800, env="CONVERSION_TIMEOUT_SECONDS")
    
    # Storage settings
    temp_dir: Path = Field(default=Path("/tmp/pdf_to_md"), env="TEMP_DIR")
    output_dir: Path = Field(default=Path("./markdown_output"), env="OUTPUT_DIR")
    
    # Model settings
    default_model: str = Field(default="opendataloader", env="DEFAULT_MODEL")
    model_cache_dir: Path = Field(default=Path("./model_cache"), env="MODEL_CACHE_DIR")
    
    # Logging settings
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    log_dir: Path = Field(default=Path("logs"), env="LOG_DIR")
    log_format: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        env="LOG_FORMAT"
    )
    
    # Security settings
    enable_rate_limiting: bool = Field(default=True, env="ENABLE_RATE_LIMITING")
    rate_limit_requests: int = Field(default=100, env="RATE_LIMIT_REQUESTS")
    rate_limit_window: int = Field(default=3600, env="RATE_LIMIT_WINDOW")  # seconds
    
    # S3/MinIO settings
    s3_endpoint_url: str = Field(default="http://localhost:9000", env="S3_ENDPOINT_URL")
    s3_access_key: str = Field(default="minio", env="S3_ACCESS_KEY")
    s3_secret_key: str = Field(default="minio123456", env="S3_SECRET_KEY")
    s3_region: str = Field(default="us-east-1", env="S3_REGION")
    s3_bucket_name: str = Field(default="knowledge-map-data", env="S3_BUCKET_NAME")

    # AI Model Service settings
    ai_model_service_host: str = Field(default="127.0.0.1", env="AI_MODEL_SERVICE_HOST")
    ai_model_service_port: int = Field(default=50059, env="AI_MODEL_SERVICE_PORT")
    ai_model_id: str = Field(default="Qwen/Qwen2.5-0.5B-Instruct", env="AI_MODEL_ID")
    ai_max_chunk_tokens: int = Field(default=18000, env="AI_MAX_CHUNK_TOKENS")
    ai_overlap_tokens: int = Field(default=1000, env="AI_OVERLAP_TOKENS")
    ai_max_generation_tokens: int = Field(default=4096, env="AI_MAX_GENERATION_TOKENS")
    ai_temperature: float = Field(default=0.3, env="AI_TEMPERATURE")
    ai_formatting_timeout: int = Field(default=600, env="AI_FORMATTING_TIMEOUT")

    model_config = ConfigDict(
        env_file = _resolve_env_file(),
        env_file_encoding = "utf-8",
        case_sensitive = False
    )


# Global settings instance
settings = Settings()

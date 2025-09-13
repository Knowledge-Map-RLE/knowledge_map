"""
Конфигурация AI сервиса для Knowledge Map.
"""

import os
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Настройки AI сервиса."""
    
    # API настройки
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8001
    
    # Модель настройки
    MODEL_NAME: str = "microsoft/DialoGPT-medium"  # Заменим на подходящую модель до 3B параметров
    MODEL_MAX_LENGTH: int = 4096
    MODEL_DEVICE: str = "auto"  # auto, cpu, cuda
    
    # PDF обработка
    PDF_MAX_PAGES: int = 100
    PDF_DPI: int = 300
    
    # S3 настройки
    S3_ENDPOINT_URL: str = "http://localhost:9000"
    S3_ACCESS_KEY: str = "minio"
    S3_SECRET_KEY: str = "minio123456"
    S3_REGION: str = "us-east-1"
    S3_BUCKET_NAME: str = "knowledge-map-pdfs"
    
    # Neo4j настройки
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "password"
    
    # API сервис
    API_SERVICE_URL: str = "http://localhost:8000"
    
    # Логирование
    LOG_LEVEL: str = "INFO"
    
    # Debug режим
    DEBUG: bool = False
    
    class Config:
        env_file = ".env"
    
    def get_database_url(self) -> str:
        """Получить URL для подключения к Neo4j."""
        uri = self.NEO4J_URI
        hostport = uri.replace("bolt://", "")
        return f"bolt://{self.NEO4J_USER}:{self.NEO4J_PASSWORD}@{hostport}"


settings = Settings()

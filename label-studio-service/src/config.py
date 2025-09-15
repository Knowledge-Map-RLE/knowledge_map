"""
Конфигурация для Label Studio сервиса
"""
import os
from pydantic import BaseSettings

class Settings(BaseSettings):
    # Label Studio настройки
    LABEL_STUDIO_URL: str = "http://localhost:8080"
    LABEL_STUDIO_API_KEY: str = "your-api-key-here"
    
    # Nutrient SDK настройки
    NUTRIENT_API_KEY: str = "your-nutrient-api-key"
    NUTRIENT_BASE_URL: str = "https://api.nutrient.io"
    
    # Настройки сервиса
    SERVICE_HOST: str = "0.0.0.0"
    SERVICE_PORT: int = 8001
    
    # Настройки базы данных
    DATABASE_URL: str = "postgresql://user:password@localhost:5432/label_studio_db"
    
    # Настройки файлов
    UPLOAD_DIR: str = "/tmp/uploads"
    MAX_FILE_SIZE: int = 50 * 1024 * 1024  # 50MB
    
    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()

import os
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # База данных
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "password"
    
    # JWT
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # Redis для сессий и rate limiting
    REDIS_URL: str = "redis://localhost:6379"
    
    # API сервис
    API_SERVICE_URL: str = "http://localhost:8000"
    
    # gRPC
    GRPC_HOST: str = "0.0.0.0"
    GRPC_PORT: int = 50051
    
    # Безопасность
    PASSWORD_MIN_LENGTH: int = 8
    RECOVERY_KEYS_COUNT: int = 10
    RECOVERY_KEY_LENGTH: int = 16
    
    # Rate limiting
    LOGIN_ATTEMPTS_LIMIT: int = 5
    LOGIN_ATTEMPTS_WINDOW: int = 300  # 5 минут
    
    class Config:
        env_file = ".env"


settings = Settings() 
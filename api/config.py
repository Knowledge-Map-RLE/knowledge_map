import os
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
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
    
    class Config:
        env_file = ".env"
    
    def get_database_url(self) -> str:
        return f"{self.NEO4J_URI}?user={self.NEO4J_USER}&password={self.NEO4J_PASSWORD}"


settings = Settings()
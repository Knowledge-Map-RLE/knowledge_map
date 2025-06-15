from pydantic_settings import BaseSettings
from typing import Optional
import os

class Settings(BaseSettings):
    # Neo4j настройки
    neo4j_uri: str = "bolt://neo4j:7687"  # Используем имя сервиса Docker
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password"
    
    # API настройки
    debug: bool = True
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    
    class Config:
        env_file = ".env"
        case_sensitive = False
        
    def get_database_url(self):
        """Получить URL для подключения к Neo4j"""
        # Убираем bolt:// если он есть в uri
        clean_uri = self.neo4j_uri.replace('bolt://', '')
        return f"bolt://{self.neo4j_user}:{self.neo4j_password}@{clean_uri}"
        
settings = Settings()
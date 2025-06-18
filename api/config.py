from pydantic_settings import BaseSettings
from typing import Optional
import os

class Settings(BaseSettings):
    # Neo4j настройки
    neo4j_uri: str = "bolt://localhost:7687"  # По умолчанию localhost, в Docker override через env
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

class Config:
    # Neo4j connection settings
    NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
    NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")  # Установите ваш пароль
    
    # Layout service settings  
    LAYOUT_SERVICE_HOST = os.getenv("LAYOUT_SERVICE_HOST", "localhost")
    LAYOUT_SERVICE_PORT = int(os.getenv("LAYOUT_SERVICE_PORT", "50051"))
    
    # API settings
    API_HOST = os.getenv("API_HOST", "0.0.0.0") 
    API_PORT = int(os.getenv("API_PORT", "8000"))
    
    @classmethod
    def get_neo4j_url(cls):
        """Получить полный URL для подключения к Neo4j"""
        return f"{cls.NEO4J_URI}"
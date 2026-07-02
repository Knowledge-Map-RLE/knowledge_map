from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False)

    grpc_host: str = Field(default="0.0.0.0", alias="GRPC_HOST")
    grpc_port: int = Field(default=50056, alias="GRPC_PORT")
    grpc_max_workers: int = Field(default=10, alias="GRPC_MAX_WORKERS")

    nlp_grpc_host: str = Field(default="localhost", alias="NLP_GRPC_HOST")
    nlp_grpc_port: int = Field(default=50055, alias="NLP_GRPC_PORT")

    ai_grpc_host: str = Field(default="localhost", alias="AI_GRPC_HOST")
    ai_grpc_port: int = Field(default=50054, alias="AI_GRPC_PORT")

    neo4j_uri: str = Field(default="bolt://localhost:7687", alias="NEO4J_URI")
    neo4j_user: str = Field(default="neo4j", alias="NEO4J_USER")
    neo4j_password: str = Field(default="password", alias="NEO4J_PASSWORD")

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    default_llm_model: str = Field(default="Qwen/Qwen2.5-0.5B-Instruct", alias="DEFAULT_LLM_MODEL")
    local_llm_model: str = Field(default="Qwen/Qwen2.5-0.5B-Instruct", alias="LOCAL_LLM_MODEL")

    hugging_face_token: str = Field(default="", alias="HUGGING_FACE_TOKEN")


settings = Settings()

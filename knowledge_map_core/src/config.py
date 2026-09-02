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

    ai_service_host: str = Field(default="localhost", alias="AI_MODEL_SERVICE_HOST")
    ai_service_port: int = Field(default=50059, alias="AI_MODEL_SERVICE_PORT")

    neo4j_uri: str = Field(default="bolt://localhost:7687", alias="NEO4J_URI")
    neo4j_user: str = Field(default="neo4j", alias="NEO4J_USER")
    neo4j_password: str = Field(default="password", alias="NEO4J_PASSWORD")

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    default_llm_model: str = Field(default="qwen/qwen3-4b", alias="DEFAULT_LLM_MODEL")
    local_llm_model: str = Field(default="qwen/qwen3-4b", alias="LOCAL_LLM_MODEL")

    hugging_face_token: str = Field(default="", alias="HUGGING_FACE_TOKEN")

    qdrant_url: str = Field(default="http://localhost:6333", alias="QDRANT_URL")
    qdrant_collection: str = Field(default="statement_embeddings", alias="QDRANT_COLLECTION")
    embedding_model: str = Field(default="all-MiniLM-L6-v2", alias="EMBEDDING_MODEL")
    embedding_dimension: int = Field(default=384, alias="EMBEDDING_DIMENSION")

    uniqueness_cosine_threshold: float = Field(default=0.95, alias="UNIQUENESS_COSINE_THRESHOLD")
    uniqueness_cosine_uncertain: float = Field(default=0.85, alias="UNIQUENESS_COSINE_UNCERTAIN")
    uniqueness_top_k: int = Field(default=20, alias="UNIQUENESS_TOP_K")
    uniqueness_wl_iterations: int = Field(default=3, alias="UNIQUENESS_WL_ITERATIONS")
    uniqueness_fsg_min_support: int = Field(default=2, alias="UNIQUENESS_FSG_MIN_SUPPORT")
    uniqueness_fsg_max_size: int = Field(default=10, alias="UNIQUENESS_FSG_MAX_SIZE")


settings = Settings()

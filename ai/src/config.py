"""Configuration for AI Model Service."""

import os
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """AI Model Service settings."""

    # gRPC Server settings
    grpc_host: str = Field(default="0.0.0.0", env="GRPC_HOST")
    grpc_port: int = Field(default=50054, env="GRPC_PORT")
    grpc_max_workers: int = Field(default=10, env="GRPC_MAX_WORKERS")

    # Model settings
    model_cache_dir: Path = Field(
        default=Path("./models"),
        env="MODEL_CACHE_DIR",
        description="Directory to cache downloaded models",
    )
    default_model: str = Field(
        default="meta-llama/Llama-3.2-1B-Instruct",
        env="DEFAULT_MODEL",
    )
    device: Literal["auto", "cpu", "cuda"] = Field(
        default="auto",
        env="MODEL_DEVICE",
        description="Device to run models on: auto (GPU if available), cpu, or cuda",
    )

    # Generation defaults
    default_max_tokens: int = Field(default=2048, env="DEFAULT_MAX_TOKENS")
    default_temperature: float = Field(default=0.7, env="DEFAULT_TEMPERATURE")
    default_top_p: float = Field(default=0.9, env="DEFAULT_TOP_P")
    default_top_k: int = Field(default=50, env="DEFAULT_TOP_K")
    default_repetition_penalty: float = Field(default=1.1, env="DEFAULT_REPETITION_PENALTY")

    # Chunking settings
    max_context_length: int = Field(
        default=100000,
        env="MAX_CONTEXT_LENGTH",
        description="Maximum context length before chunking",
    )
    chunk_overlap: int = Field(
        default=200,
        env="CHUNK_OVERLAP",
        description="Overlap between chunks in tokens",
    )

    # Logging
    log_level: str = Field(default="INFO", env="LOG_LEVEL")

    # Resource limits
    max_batch_size: int = Field(default=1, env="MAX_BATCH_SIZE")
    timeout_seconds: int = Field(default=300, env="TIMEOUT_SECONDS")

    class Config:
        """Pydantic config."""

        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# Global settings instance
settings = Settings()

# Ensure model cache directory exists
settings.model_cache_dir.mkdir(parents=True, exist_ok=True)

"""Configuration for NLP microservice."""

import os
from pathlib import Path
from typing import Optional
from pydantic import Field, ConfigDict
from pydantic_settings import BaseSettings


class NLPConfig(BaseSettings):
    """Configuration for NLP service."""

    # Server settings
    host: str = "0.0.0.0"
    port: int = 50055
    max_workers: int = 10

    # Model cache directory
    model_cache_dir: Path = Field(
        default=Path("./models"),
        env="MODEL_CACHE_DIR",
        description="Directory to cache downloaded NLP models",
    )

    # NLP processors configuration
    enable_spacy: bool = True
    enable_nltk: bool = False  # Disable other processors
    enable_stanza: bool = False  # Disable other processors
    enable_udpipe: bool = False  # Disable other processors

    # Voting system configuration
    min_agreement: int = 1  # Only need 1 processor (spaCy)
    enable_voting: bool = False  # Disable voting by default

    # Language models
    spacy_model: str = "en_core_sci_scibert"

    stanza_lang: str = "en"

    # Performance settings
    max_text_length: int = 1000000  # Maximum text length to process
    batch_size: int = 32

    # Markdown validation settings
    validate_markdown_on_save: bool = True
    max_markdown_length: int = 5000000  # 5MB max for markdown documents
    require_references_section: bool = True

    # Logging
    log_level: str = "INFO"

    # Model configuration for pydantic v2: set env prefix and ignore extra env vars
    model_config = ConfigDict(
        env_prefix="NLP_",
        case_sensitive=False,
        extra="ignore",
    )


# Global config instance
_config: Optional[NLPConfig] = None


def get_config() -> NLPConfig:
    """Get or create global config instance."""
    global _config
    if _config is None:
        _config = NLPConfig()
    return _config

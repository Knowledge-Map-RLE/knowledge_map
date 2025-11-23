"""Configuration for NLP microservice."""

import os
from typing import Optional
from pydantic_settings import BaseSettings


class NLPConfig(BaseSettings):
    """Configuration for NLP service."""

    # Server settings
    host: str = "0.0.0.0"
    port: int = 50055
    max_workers: int = 10

    # NLP processors configuration
    enable_spacy: bool = True
    enable_nltk: bool = True
    enable_stanza: bool = True
    enable_udpipe: bool = True

    # Voting system configuration
    min_agreement: int = 2  # Minimum processors that must agree
    enable_voting: bool = True

    # Language models
    spacy_model: str = "ru_core_news_sm"  # Russian language model
    stanza_lang: str = "ru"

    # Performance settings
    max_text_length: int = 1000000  # Maximum text length to process
    batch_size: int = 32

    # Logging
    log_level: str = "INFO"

    class Config:
        env_prefix = "NLP_"
        case_sensitive = False
        env_file = ".env"
        env_file_encoding = "utf-8"


# Global config instance
_config: Optional[NLPConfig] = None


def get_config() -> NLPConfig:
    """Get or create global config instance."""
    global _config
    if _config is None:
        _config = NLPConfig()
    return _config

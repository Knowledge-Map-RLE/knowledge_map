"""
Model loading and caching module.

This is the ONLY stateful module in the functional architecture.
All model loading and initialization happens here.

All other modules use the models returned by this module and remain pure.
"""

from functools import lru_cache
import logging
from typing import Optional

import spacy
from spacy.language import Language

logger = logging.getLogger(__name__)


@lru_cache(maxsize=10)
def load_spacy_model(model_name: str) -> Language:
    """
    Load a spaCy model with caching.

    Args:
        model_name: Name of the spaCy model (e.g., "en_core_web_sm")

    Returns:
        Loaded spaCy Language object

    Raises:
        OSError: If model is not found
    """
    logger.info(f"Loading spaCy model: {model_name}")

    try:
        nlp = spacy.load(model_name)
        logger.info(f"Successfully loaded {model_name}")
        return nlp
    except OSError as e:
        logger.error(f"Failed to load model {model_name}: {e}")
        raise


def setup_spacy_models(models: list[str] = None) -> None:
    """
    Pre-load spaCy models to ensure they are available.

    This is useful for warming up the cache at application startup.

    Args:
        models: List of model names to load. If None, uses default models.

    Example:
        >>> setup_spacy_models(["en_core_web_sm", "en_core_web_md"])
    """
    if models is None:
        models = ["en_core_web_sm"]

    logger.info(f"Setting up models: {models}")
    for model_name in models:
        try:
            load_spacy_model(model_name)
            logger.info(f"✓ Model {model_name} loaded")
        except OSError as e:
            logger.warning(f"✗ Failed to load {model_name}: {e}")


def clear_model_cache() -> None:
    """
    Clear the model cache.

    Useful for testing or freeing memory.
    """
    load_spacy_model.cache_clear()
    logger.info("Model cache cleared")


def get_model_cache_info() -> dict:
    """
    Get information about the model cache.

    Returns:
        Cache info with hits, misses, maxsize, currsize
    """
    info = load_spacy_model.cache_info()
    return {
        "hits": info.hits,
        "misses": info.misses,
        "maxsize": info.maxsize,
        "currsize": info.currsize,
    }

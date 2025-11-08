"""
NLP module for automatic text annotation.

This module provides an extensible architecture for integrating multiple
NLP processors (spaCy, custom models, etc.) to automatically annotate text.
"""

from .base import BaseNLPProcessor, AnnotationSuggestion, ProcessingResult
from .nlp_manager import NLPManager

__all__ = [
    "BaseNLPProcessor",
    "AnnotationSuggestion",
    "ProcessingResult",
    "NLPManager"
]

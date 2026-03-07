"""
NLP module for automatic text annotation.

This module provides a functional architecture for NLP processing using
spaCy as the core NLP engine.

Main entry points:
- tokenize(text) - Level 1: Tokenization
- analyze_morphology(text) - Level 2: Morphology
- analyze_syntax(text) - Level 3: Syntax
- analyze_text(text) - Full analysis (Levels 1-3)
"""

# Functional architecture
from .pipelines import (
    tokenize,
    analyze_morphology,
    analyze_syntax,
    analyze_text,
)

from .unified_types import (
    UnifiedDocument,
    UnifiedSentence,
    UnifiedToken,
    UnifiedDependency,
    UnifiedEntity,
    LinguisticLevel,
)

# Keep old imports for backward compatibility (if available)
try:
    from .base import BaseNLPProcessor, AnnotationSuggestion, ProcessingResult
    from .nlp_manager import NLPManager
except ImportError:
    # Old modules might not be available
    pass

__all__ = [
    # Main pipelines
    "tokenize",
    "analyze_morphology",
    "analyze_syntax",
    "analyze_text",

    # Types
    "UnifiedDocument",
    "UnifiedSentence",
    "UnifiedToken",
    "UnifiedDependency",
    "UnifiedEntity",
    "LinguisticLevel",

    # Old API (if available)
    "BaseNLPProcessor",
    "AnnotationSuggestion",
    "ProcessingResult",
    "NLPManager",
]

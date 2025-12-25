"""
NLP Pipelines - Complete processing pipelines from text to analysis.

Each pipeline file is self-contained and contains a complete pipeline function.
"""

from .tokenization import tokenize
from .morphology import analyze_morphology
from .syntax import analyze_syntax
from .full_analysis import analyze_text

__all__ = [
    "tokenize",
    "analyze_morphology",
    "analyze_syntax",
    "analyze_text",
]

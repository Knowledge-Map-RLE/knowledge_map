"""
Full multi-level analysis pipeline (Levels 1-3).

This is the main entry point for complete text analysis.

PIPELINE FLOW:
    This pipeline simply delegates to analyze_syntax, which includes
    all three levels (tokenization, morphology, syntax).

This is a self-contained pipeline. All dependencies are explicit.
"""

from typing import Optional

from .syntax import analyze_syntax
from ..types import UnifiedDocument


def analyze_text(
    text: str,
    model_name: str = "en_core_web_sm",
    doc_id: Optional[str] = None
) -> UnifiedDocument:
    """
    PIPELINE: Complete multi-level text analysis (Levels 1-3).

    This is the main entry point for analyzing text. It returns a fully
    annotated document with:
    - Tokenization
    - Morphological analysis
    - Syntactic analysis (dependencies, entities, phrases)

    All three levels (1, 2, 3) are processed.

    Args:
        text: Input text to analyze
        model_name: spaCy model name (default: "en_core_web_sm")
        doc_id: Document ID (auto-generated if None)

    Returns:
        Fully analyzed UnifiedDocument with all levels (1-3) processed

    Example:
        >>> doc = analyze_text("Apple released a new iPhone.")
        >>> doc.sentences[0].tokens[0].text
        'Apple'
        >>> doc.sentences[0].tokens[0].pos
        'PROPN'
        >>> len(doc.sentences[0].dependencies)
        4
        >>> doc.sentences[0].entities[0].entity_type
        'ORG'
    """
    return analyze_syntax(text, model_name, doc_id)

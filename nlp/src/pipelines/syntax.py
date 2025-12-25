"""
Syntax analysis pipeline (Level 3).

This pipeline handles syntactic analysis including dependency parsing
and phrase extraction.

PIPELINE FLOW:
    text (str)
        → load_spacy_model(model_name)
        → spacy_model(text)
        → spacy.Doc
        → document_to_unified(doc)  # Includes deps, entities, phrases
        → UnifiedDocument
        (update processed_levels)

This is a self-contained pipeline. All dependencies are explicit.
"""

from typing import Optional

from ..models import load_spacy_model
from ..transforms.spacy_to_unified import (
    document_to_unified,
    extract_noun_phrases,
    extract_verb_phrases,
)
from ..types import UnifiedDocument, LinguisticLevel


def analyze_syntax(
    text: str,
    model_name: str = "en_core_web_sm",
    doc_id: Optional[str] = None
) -> UnifiedDocument:
    """
    PIPELINE: Syntactic analysis (Level 3).

    This is the most comprehensive pipeline. It performs:
    - Tokenization
    - Morphological analysis
    - Dependency parsing
    - Named entity recognition
    - Phrase extraction (NP, VP)

    Args:
        text: Input text
        model_name: spaCy model name (default: "en_core_web_sm")
        doc_id: Document ID (auto-generated if None)

    Returns:
        UnifiedDocument with full syntactic analysis
        processed_levels = [TOKENIZATION, MORPHOLOGY, SYNTAX]

    Example:
        >>> doc = analyze_syntax("Apple released a new iPhone.")
        >>> token = doc.sentences[0].tokens[0]
        >>> token.text
        'Apple'
        >>> token.pos
        'PROPN'
        >>> len(doc.sentences[0].dependencies)
        4
        >>> len(doc.sentences[0].entities)
        1
        >>> doc.sentences[0].entities[0].entity_type
        'ORG'
    """
    # Load spaCy model (cached after first load)
    nlp = load_spacy_model(model_name)

    # Process text with spaCy (this is the most expensive operation)
    spacy_doc = nlp(text)

    # Convert to unified format
    # Note: document_to_unified already extracts dependencies and entities
    unified_doc = document_to_unified(
        spacy_doc,
        doc_id=doc_id,
        confidence=1.0,
        source="spacy"
    )

    # Mark that all three levels were processed
    unified_doc.processed_levels = [
        LinguisticLevel.TOKENIZATION,
        LinguisticLevel.MORPHOLOGY,
        LinguisticLevel.SYNTAX,
    ]

    return unified_doc

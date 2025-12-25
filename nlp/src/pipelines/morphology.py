"""
Morphology analysis pipeline (Level 2).

This pipeline handles morphological analysis and POS tagging.

PIPELINE FLOW:
    text (str)
        → load_spacy_model(model_name)
        → spacy_model(text)
        → spacy.Doc
        → document_to_unified(doc)  # Includes morphology
        → UnifiedDocument
        (update processed_levels)

This is a self-contained pipeline. All dependencies are explicit.
"""

from typing import Optional

from ..models import load_spacy_model
from ..transforms.spacy_to_unified import document_to_unified
from ..types import UnifiedDocument, LinguisticLevel


def analyze_morphology(
    text: str,
    model_name: str = "en_core_web_sm",
    doc_id: Optional[str] = None
) -> UnifiedDocument:
    """
    PIPELINE: Morphological analysis (Level 2).

    This pipeline analyzes morphological features (tense, number, person, etc.).

    Note: In spaCy, morphological analysis is performed automatically during
    tokenization (Level 1), so this pipeline is effectively the same as tokenization
    but marks the document as having morphological analysis completed.

    Args:
        text: Input text
        model_name: spaCy model name (default: "en_core_web_sm")
        doc_id: Document ID (auto-generated if None)

    Returns:
        UnifiedDocument with tokenization and morphology
        processed_levels = [TOKENIZATION, MORPHOLOGY]

    Example:
        >>> doc = analyze_morphology("The cats ran.")
        >>> token = doc.sentences[0].tokens[1]  # "cats"
        >>> token.text
        'cats'
        >>> token.morph
        {'Number': 'Plur'}
    """
    # Load spaCy model (cached after first load)
    nlp = load_spacy_model(model_name)

    # Process text with spaCy
    spacy_doc = nlp(text)

    # Convert to unified format
    # Note: spaCy extracts morphological features during tokenization
    unified_doc = document_to_unified(
        spacy_doc,
        doc_id=doc_id,
        confidence=1.0,
        source="spacy"
    )

    # Mark that tokenization and morphology levels were processed
    unified_doc.processed_levels = [
        LinguisticLevel.TOKENIZATION,
        LinguisticLevel.MORPHOLOGY,
    ]

    return unified_doc

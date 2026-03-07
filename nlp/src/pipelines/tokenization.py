"""
Tokenization pipeline (Level 1).

This pipeline handles text tokenization and basic POS tagging.

PIPELINE FLOW:
    text (str)
        → load_spacy_model(model_name)
        → spacy_model(text)
        → spacy.Doc
        → document_to_unified(doc)
        → UnifiedDocument

This is a complete, self-contained pipeline. All dependencies are explicit.
"""

from typing import Optional

from ..models import load_spacy_model
from ..transforms.spacy_to_unified import document_to_unified
from ..unified_types import UnifiedDocument, LinguisticLevel


def tokenize(
    text: str,
    model_name: str = "en_core_web_sm",
    doc_id: Optional[str] = None
) -> UnifiedDocument:
    """
    PIPELINE: Text tokenization with POS tagging (Level 1).

    This is the entry point for tokenization. It orchestrates:
    1. Loading spaCy model (cached)
    2. Processing text with spaCy
    3. Converting spaCy output to unified format

    Pure composition of functions - the side effect of loading the model
    happens only in load_spacy_model (which caches it).

    Args:
        text: Input text to tokenize
        model_name: spaCy model name (default: "en_core_web_sm")
        doc_id: Document ID (auto-generated if None)

    Returns:
        UnifiedDocument with tokenization and POS tagging
        processed_levels = [TOKENIZATION]

    Example:
        >>> doc = tokenize("The cat sat on the mat.")
        >>> len(doc.sentences)
        1
        >>> len(doc.sentences[0].tokens)
        8
        >>> doc.sentences[0].tokens[0].text
        'The'
        >>> doc.sentences[0].tokens[0].pos
        'DET'
    """
    # Load spaCy model (cached after first load)
    nlp = load_spacy_model(model_name)

    # Process text with spaCy
    spacy_doc = nlp(text)

    # Convert to unified format
    unified_doc = document_to_unified(
        spacy_doc,
        doc_id=doc_id,
        confidence=1.0,
        source="spacy"
    )

    # Mark that only tokenization level was processed
    unified_doc.processed_levels = [LinguisticLevel.TOKENIZATION]

    return unified_doc

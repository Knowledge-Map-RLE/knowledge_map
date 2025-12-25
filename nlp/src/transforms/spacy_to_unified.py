"""
Pure transformation functions from spaCy objects to Unified types.

This module contains only pure functions (no side effects, no state).
All functions are deterministic and referentially transparent.
"""

from typing import List, Dict, Optional, Set
from uuid import uuid4

from spacy.tokens import Doc, Span, Token

from ..types import (
    UnifiedToken,
    UnifiedDependency,
    UnifiedEntity,
    UnifiedPhrase,
    UnifiedSentence,
    UnifiedDocument,
    LinguisticLevel,
    SCIENTIFIC_ENTITY_TYPES,
)


# ============================================================================
# Token transformation functions
# ============================================================================

def token_to_unified(
    spacy_token: Token,
    sentence_start_char: int,
    token_idx: int,
    confidence: float = 1.0,
    source: str = "spacy"
) -> UnifiedToken:
    """
    Convert a spaCy Token to a UnifiedToken.

    Pure function - same input always produces same output.

    Args:
        spacy_token: spaCy Token object
        sentence_start_char: Character offset of sentence start in document
        token_idx: Index of token in sentence
        confidence: Confidence score for this token (default: 1.0)
        source: Source name (default: "spacy")

    Returns:
        UnifiedToken with extracted linguistic features
    """
    # Extract basic info
    text = spacy_token.text
    lemma = spacy_token.lemma_
    pos = spacy_token.pos_
    pos_fine = spacy_token.tag_
    start_char = sentence_start_char + spacy_token.idx
    end_char = start_char + len(text)

    # Extract morphological features
    morph = _extract_morph_features(spacy_token)

    # Create token
    unified_token = UnifiedToken(
        idx=token_idx,
        text=text,
        start_char=start_char,
        end_char=end_char,
        lemma=lemma,
        pos=pos,
        pos_fine=pos_fine,
        morph=morph,
        confidence=confidence,
        sources=[source],
        is_stop=spacy_token.is_stop,
        is_punct=spacy_token.is_punct,
        is_space=spacy_token.is_space,
    )

    return unified_token


def _extract_morph_features(spacy_token: Token) -> Dict[str, str]:
    """
    Extract morphological features from spaCy token.

    Pure helper function.

    Args:
        spacy_token: spaCy Token

    Returns:
        Dictionary of morphological features (e.g., {"Tense": "Past", "Number": "Sing"})
    """
    morph = {}

    # spaCy provides morphological features directly
    if spacy_token.morph:
        for feature in spacy_token.morph:
            if '=' in feature:
                key, value = feature.split('=', 1)
                morph[key] = value

    return morph


# ============================================================================
# Dependency transformation functions
# ============================================================================

def dependency_to_unified(
    spacy_token: Token,
    confidence: float = 1.0,
    source: str = "spacy"
) -> UnifiedDependency:
    """
    Convert a spaCy dependency (represented via Token) to UnifiedDependency.

    Pure function - extracts head-dependent relationship from token.

    Args:
        spacy_token: spaCy Token (dependent)
        confidence: Confidence score (default: 1.0)
        source: Source name (default: "spacy")

    Returns:
        UnifiedDependency representing the arc from head to dependent
    """
    unified_dep = UnifiedDependency(
        head_idx=spacy_token.head.i,
        dependent_idx=spacy_token.i,
        relation=spacy_token.dep_,
        confidence=confidence,
        sources=[source],
    )

    return unified_dep


# ============================================================================
# Entity transformation functions
# ============================================================================

def entity_to_unified(
    spacy_entity: Span,
    tokens: List[UnifiedToken],
    confidence: float = 1.0,
    source: str = "spacy"
) -> UnifiedEntity:
    """
    Convert a spaCy entity (Span) to UnifiedEntity.

    Pure function - filters tokens and creates entity.

    Args:
        spacy_entity: spaCy named entity (Span)
        tokens: All tokens in the sentence
        confidence: Confidence score (default: 1.0)
        source: Source name (default: "spacy")

    Returns:
        UnifiedEntity with extracted information
    """
    # Filter tokens that belong to this entity
    entity_tokens = [
        t for t in tokens
        if spacy_entity.start <= t.idx < spacy_entity.end
    ]

    # Determine if it's a scientific entity
    entity_type = spacy_entity.label_
    is_scientific = entity_type in SCIENTIFIC_ENTITY_TYPES

    unified_entity = UnifiedEntity(
        entity_type=entity_type,
        start_idx=spacy_entity.start,
        end_idx=spacy_entity.end,
        tokens=entity_tokens,
        confidence=confidence,
        sources=[source],
        is_scientific=is_scientific,
    )

    return unified_entity


# ============================================================================
# Phrase extraction functions
# ============================================================================

def extract_noun_phrases(
    spacy_sent: Span,
    tokens: List[UnifiedToken]
) -> List[UnifiedPhrase]:
    """
    Extract noun phrases from a spaCy sentence.

    Pure function - uses spaCy's noun_chunks to identify phrases.

    Args:
        spacy_sent: spaCy sentence (Span)
        tokens: All tokens in the sentence

    Returns:
        List of UnifiedPhrase objects representing noun phrases
    """
    phrases = []

    for chunk in spacy_sent.noun_chunks:
        # Find tokens in this chunk
        chunk_tokens = [
            t for t in tokens
            if chunk.start <= t.idx < chunk.end
        ]

        if chunk_tokens:
            # Find head token (rightmost noun by default in spaCy)
            head_idx = chunk.root.i

            phrase = UnifiedPhrase(
                phrase_type="NP",
                start_idx=chunk.start,
                end_idx=chunk.end,
                tokens=chunk_tokens,
                head_idx=head_idx,
                confidence=1.0,
                sources=["spacy"],
            )
            phrases.append(phrase)

    return phrases


def extract_verb_phrases(
    spacy_sent: Span,
    tokens: List[UnifiedToken]
) -> List[UnifiedPhrase]:
    """
    Extract verb phrases from a spaCy sentence.

    Pure function - uses dependency relations to identify verb phrases.

    Args:
        spacy_sent: spaCy sentence (Span)
        tokens: All tokens in the sentence

    Returns:
        List of UnifiedPhrase objects representing verb phrases
    """
    phrases = []

    # Find all verbs
    verb_indices = {
        i: token for i, token in enumerate(spacy_sent)
        if token.pos_ == "VERB"
    }

    # For each verb, create a phrase including its modifiers
    for verb_idx, verb_token in verb_indices.items():
        # Get all children of the verb
        children = [token for token in spacy_sent if token.head == verb_token]

        # Create span from first child/verb to last child/verb
        start_idx = min(
            [verb_token.i] + [c.i for c in children]
        )
        end_idx = max(
            [verb_token.i + 1] + [c.i + 1 for c in children]
        )

        # Get tokens in this phrase
        phrase_tokens = [
            t for t in tokens
            if start_idx <= t.idx < end_idx
        ]

        if phrase_tokens:
            phrase = UnifiedPhrase(
                phrase_type="VP",
                start_idx=start_idx,
                end_idx=end_idx,
                tokens=phrase_tokens,
                head_idx=verb_token.i,
                confidence=1.0,
                sources=["spacy"],
            )
            phrases.append(phrase)

    return phrases


# ============================================================================
# Sentence transformation functions
# ============================================================================

def sentence_to_unified(
    spacy_sent: Span,
    sent_idx: int,
    doc_start_char: int = 0,
    confidence: float = 1.0,
    source: str = "spacy"
) -> UnifiedSentence:
    """
    Convert a spaCy sentence (Span) to UnifiedSentence.

    This is the main sentence transformation function that orchestrates
    conversion of all components (tokens, dependencies, entities, phrases).

    Pure function - deterministic transformation.

    Args:
        spacy_sent: spaCy sentence (Span)
        sent_idx: Index of sentence in document
        doc_start_char: Character offset of document start (default: 0)
        confidence: Confidence score (default: 1.0)
        source: Source name (default: "spacy")

    Returns:
        Complete UnifiedSentence with all linguistic information
    """
    sentence_start_char = doc_start_char + spacy_sent.start_char

    # Convert tokens
    tokens = []
    for token_idx, spacy_token in enumerate(spacy_sent):
        unified_token = token_to_unified(
            spacy_token,
            sentence_start_char=sentence_start_char,
            token_idx=token_idx,
            confidence=confidence,
            source=source
        )
        tokens.append(unified_token)

    # Convert dependencies
    dependencies = []
    root_idx = None
    for spacy_token in spacy_sent:
        if spacy_token.dep_ == 'ROOT':
            root_idx = spacy_token.i
        elif spacy_token.head in spacy_sent:
            # Only add if head is within sentence
            unified_dep = dependency_to_unified(
                spacy_token,
                confidence=confidence,
                source=source
            )
            dependencies.append(unified_dep)

    # Convert entities
    entities = []
    for spacy_entity in spacy_sent.ents:
        unified_entity = entity_to_unified(
            spacy_entity,
            tokens=tokens,
            confidence=confidence,
            source=source
        )
        entities.append(unified_entity)

    # Extract phrases
    noun_phrases = extract_noun_phrases(spacy_sent, tokens)
    verb_phrases = extract_verb_phrases(spacy_sent, tokens)
    phrases = noun_phrases + verb_phrases

    # Create unified sentence
    unified_sentence = UnifiedSentence(
        idx=sent_idx,
        text=spacy_sent.text,
        start_char=sentence_start_char,
        end_char=sentence_start_char + len(spacy_sent.text),
        tokens=tokens,
        dependencies=dependencies,
        entities=entities,
        phrases=phrases,
        root_idx=root_idx,
        confidence=confidence,
    )

    return unified_sentence


# ============================================================================
# Document transformation functions
# ============================================================================

def document_to_unified(
    spacy_doc: Doc,
    doc_id: Optional[str] = None,
    confidence: float = 1.0,
    source: str = "spacy"
) -> UnifiedDocument:
    """
    Convert a spaCy Doc to UnifiedDocument.

    This is the main document transformation function - the entry point
    for all text processing through spaCy.

    Pure function - deterministic transformation.

    Args:
        spacy_doc: spaCy Doc object (fully processed)
        doc_id: Document ID (auto-generated if None)
        confidence: Confidence score (default: 1.0)
        source: Source name (default: "spacy")

    Returns:
        Complete UnifiedDocument with all sentences and linguistic levels
    """
    # Generate doc_id if not provided
    if doc_id is None:
        doc_id = str(uuid4())

    # Convert sentences
    sentences = []
    for sent_idx, spacy_sent in enumerate(spacy_doc.sents):
        unified_sent = sentence_to_unified(
            spacy_sent,
            sent_idx=sent_idx,
            doc_start_char=0,
            confidence=confidence,
            source=source
        )
        sentences.append(unified_sent)

    # Extract document-level entities
    doc_entities = []
    all_tokens = [t for sent in sentences for t in sent.tokens]
    for spacy_entity in spacy_doc.ents:
        unified_entity = entity_to_unified(
            spacy_entity,
            tokens=all_tokens,
            confidence=confidence,
            source=source
        )
        doc_entities.append(unified_entity)

    # Create unified document
    unified_doc = UnifiedDocument(
        doc_id=doc_id,
        text=spacy_doc.text,
        sentences=sentences,
        entities=doc_entities,
        processed_levels=[
            LinguisticLevel.TOKENIZATION,
            LinguisticLevel.MORPHOLOGY,
            LinguisticLevel.SYNTAX,
        ],
    )

    return unified_doc

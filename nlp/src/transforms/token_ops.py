"""
Pure functions for token operations.

All functions in this module are pure - they have no side effects and always
produce the same output for the same input.
"""

from typing import List, Dict, Set
from collections import Counter

from ..unified_types import UnifiedToken, CONTENT_POS_TAGS, STOP_POS_TAGS


# ============================================================================
# Basic filtering functions
# ============================================================================

def extract_content_words(tokens: List[UnifiedToken]) -> List[UnifiedToken]:
    """
    Extract only content words (remove stop words).

    Pure function - filters based on POS tag.

    Args:
        tokens: List of tokens

    Returns:
        Tokens that are not stop words
    """
    return [t for t in tokens if t.pos in CONTENT_POS_TAGS]


def extract_function_words(tokens: List[UnifiedToken]) -> List[UnifiedToken]:
    """
    Extract only function words (stop words).

    Pure function.

    Args:
        tokens: List of tokens

    Returns:
        Tokens that are stop words
    """
    return [t for t in tokens if t.pos in STOP_POS_TAGS]


def filter_by_pos(
    tokens: List[UnifiedToken],
    pos_tags: Set[str]
) -> List[UnifiedToken]:
    """
    Filter tokens by POS tags.

    Pure function.

    Args:
        tokens: List of tokens
        pos_tags: Set of POS tags to keep

    Returns:
        Tokens matching specified POS tags
    """
    return [t for t in tokens if t.pos in pos_tags]


def filter_by_lemma(
    tokens: List[UnifiedToken],
    lemmas: Set[str]
) -> List[UnifiedToken]:
    """
    Filter tokens by lemmas.

    Pure function.

    Args:
        tokens: List of tokens
        lemmas: Set of lemmas to keep

    Returns:
        Tokens with specified lemmas
    """
    return [t for t in tokens if t.lemma in lemmas]


def exclude_stop_tokens(tokens: List[UnifiedToken]) -> List[UnifiedToken]:
    """
    Remove punctuation and stop tokens.

    Pure function.

    Args:
        tokens: List of tokens

    Returns:
        Tokens that are neither punctuation nor stop words
    """
    return [
        t for t in tokens
        if not t.is_punct and not t.is_stop and not t.is_space
    ]


# ============================================================================
# Grouping and aggregation functions
# ============================================================================

def group_by_lemma(
    tokens: List[UnifiedToken]
) -> Dict[str, List[UnifiedToken]]:
    """
    Group tokens by lemma.

    Pure function.

    Args:
        tokens: List of tokens

    Returns:
        Dictionary mapping lemmas to lists of tokens
    """
    groups: Dict[str, List[UnifiedToken]] = {}
    for token in tokens:
        if token.lemma not in groups:
            groups[token.lemma] = []
        groups[token.lemma].append(token)
    return groups


def group_by_pos(
    tokens: List[UnifiedToken]
) -> Dict[str, List[UnifiedToken]]:
    """
    Group tokens by POS tag.

    Pure function.

    Args:
        tokens: List of tokens

    Returns:
        Dictionary mapping POS tags to lists of tokens
    """
    groups: Dict[str, List[UnifiedToken]] = {}
    for token in tokens:
        if token.pos not in groups:
            groups[token.pos] = []
        groups[token.pos].append(token)
    return groups


def group_by_morph_feature(
    tokens: List[UnifiedToken],
    feature: str
) -> Dict[str, List[UnifiedToken]]:
    """
    Group tokens by a morphological feature value.

    Pure function.

    Args:
        tokens: List of tokens
        feature: Feature name (e.g., "Tense", "Number")

    Returns:
        Dictionary mapping feature values to lists of tokens
    """
    groups: Dict[str, List[UnifiedToken]] = {}
    for token in tokens:
        if feature in token.morph:
            value = token.morph[feature]
            if value not in groups:
                groups[value] = []
            groups[value].append(token)
    return groups


# ============================================================================
# Statistics functions
# ============================================================================

def get_pos_distribution(tokens: List[UnifiedToken]) -> Dict[str, int]:
    """
    Get POS tag frequency distribution.

    Pure function.

    Args:
        tokens: List of tokens

    Returns:
        Dictionary mapping POS tags to frequency counts
    """
    counter = Counter(t.pos for t in tokens)
    return dict(counter)


def get_lemma_frequency(tokens: List[UnifiedToken]) -> Dict[str, int]:
    """
    Get lemma frequency distribution.

    Pure function.

    Args:
        tokens: List of tokens

    Returns:
        Dictionary mapping lemmas to frequency counts
    """
    counter = Counter(t.lemma for t in tokens)
    return dict(counter)


def get_morph_feature_distribution(
    tokens: List[UnifiedToken],
    feature: str
) -> Dict[str, int]:
    """
    Get frequency distribution of a morphological feature.

    Pure function.

    Args:
        tokens: List of tokens
        feature: Feature name (e.g., "Tense")

    Returns:
        Dictionary mapping feature values to frequency counts
    """
    values = [t.morph.get(feature) for t in tokens if feature in t.morph]
    counter = Counter(values)
    return dict(counter)


def get_confidence_stats(tokens: List[UnifiedToken]) -> Dict[str, float]:
    """
    Calculate confidence statistics for tokens.

    Pure function.

    Args:
        tokens: List of tokens

    Returns:
        Dictionary with min, max, mean confidence scores
    """
    if not tokens:
        return {"min": 0.0, "max": 0.0, "mean": 0.0}

    confidences = [t.confidence for t in tokens]
    return {
        "min": min(confidences),
        "max": max(confidences),
        "mean": sum(confidences) / len(confidences),
    }


# ============================================================================
# Search and lookup functions
# ============================================================================

def find_token_by_index(
    tokens: List[UnifiedToken],
    idx: int
) -> UnifiedToken | None:
    """
    Find token by its index in sentence.

    Pure function.

    Args:
        tokens: List of tokens
        idx: Token index

    Returns:
        Token with matching index, or None
    """
    return next((t for t in tokens if t.idx == idx), None)


def find_tokens_by_text(
    tokens: List[UnifiedToken],
    text: str
) -> List[UnifiedToken]:
    """
    Find all tokens matching text (case-sensitive).

    Pure function.

    Args:
        tokens: List of tokens
        text: Text to search for

    Returns:
        Tokens matching the text
    """
    return [t for t in tokens if t.text == text]


def find_tokens_by_morph(
    tokens: List[UnifiedToken],
    feature: str,
    value: str
) -> List[UnifiedToken]:
    """
    Find all tokens with specific morphological feature value.

    Pure function.

    Args:
        tokens: List of tokens
        feature: Feature name (e.g., "Tense")
        value: Feature value (e.g., "Past")

    Returns:
        Tokens with matching morphological feature
    """
    return [
        t for t in tokens
        if t.morph.get(feature) == value
    ]


# ============================================================================
# Transformation functions
# ============================================================================

def to_text(tokens: List[UnifiedToken]) -> str:
    """
    Convert tokens back to text.

    Pure function - joins tokens preserving whitespace info.

    Args:
        tokens: List of tokens

    Returns:
        Reconstructed text
    """
    if not tokens:
        return ""

    parts = []
    for i, token in enumerate(tokens):
        if i > 0:
            # Add spacing between tokens if not punctuation or space
            if not token.is_punct and not token.is_space:
                parts.append(" ")
        parts.append(token.text)

    return "".join(parts)


def get_lemmas(tokens: List[UnifiedToken]) -> List[str]:
    """
    Extract all lemmas in order.

    Pure function.

    Args:
        tokens: List of tokens

    Returns:
        List of lemmas
    """
    return [t.lemma for t in tokens]


def get_pos_tags(tokens: List[UnifiedToken]) -> List[str]:
    """
    Extract all POS tags in order.

    Pure function.

    Args:
        tokens: List of tokens

    Returns:
        List of POS tags
    """
    return [t.pos for t in tokens]


def get_span_text(
    tokens: List[UnifiedToken],
    start_idx: int,
    end_idx: int
) -> str:
    """
    Get text of a token span.

    Pure function.

    Args:
        tokens: List of tokens
        start_idx: Start index (inclusive)
        end_idx: End index (exclusive)

    Returns:
        Text of the span
    """
    span_tokens = [t for t in tokens if start_idx <= t.idx < end_idx]
    return to_text(span_tokens)

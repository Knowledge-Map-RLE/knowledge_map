"""
Morphological analysis and statistics functions.

Pure functions for analyzing morphological features in documents.
"""

from typing import Dict, List
from collections import Counter

from ..types import UnifiedDocument, UnifiedToken
from ..transforms.token_ops import (
    get_pos_distribution,
    get_morph_feature_distribution,
    find_tokens_by_morph,
    group_by_pos,
)


# ============================================================================
# Document-level statistics
# ============================================================================

def get_document_pos_distribution(doc: UnifiedDocument) -> Dict[str, int]:
    """
    Get POS tag distribution across entire document.

    Pure function.

    Args:
        doc: UnifiedDocument

    Returns:
        Dictionary mapping POS tags to counts
    """
    all_tokens = [t for sent in doc.sentences for t in sent.tokens]
    return get_pos_distribution(all_tokens)


def get_document_morphology_features(
    doc: UnifiedDocument
) -> Dict[str, Dict[str, int]]:
    """
    Get all morphological features and their distributions in document.

    Pure function.

    Args:
        doc: UnifiedDocument

    Returns:
        Dictionary mapping feature names to value distributions
    """
    all_tokens = [t for sent in doc.sentences for t in sent.tokens]

    # Collect all feature names
    features: Dict[str, Dict[str, int]] = {}

    for token in all_tokens:
        for feature, value in token.morph.items():
            if feature not in features:
                features[feature] = {}
            features[feature][value] = features[feature].get(value, 0) + 1

    return features


def get_document_morphology_statistics(
    doc: UnifiedDocument
) -> Dict[str, any]:
    """
    Get comprehensive morphological statistics for document.

    Pure function.

    Args:
        doc: UnifiedDocument

    Returns:
        Dictionary with various statistics
    """
    all_tokens = [t for sent in doc.sentences for t in sent.tokens]

    return {
        "total_tokens": len(all_tokens),
        "unique_lemmas": len(set(t.lemma for t in all_tokens)),
        "unique_pos_tags": len(set(t.pos for t in all_tokens)),
        "pos_distribution": get_pos_distribution(all_tokens),
        "morphology_features": get_document_morphology_features(doc),
        "avg_morph_features_per_token": _average_morph_features(all_tokens),
    }


def _average_morph_features(tokens: List[UnifiedToken]) -> float:
    """Helper: calculate average morphological features per token."""
    if not tokens:
        return 0.0
    total_features = sum(len(t.morph) for t in tokens)
    return total_features / len(tokens)


# ============================================================================
# Sentence-level statistics
# ============================================================================

def get_sentence_morphology_stats(
    doc: UnifiedDocument,
    sent_idx: int
) -> Dict[str, any]:
    """
    Get morphological statistics for a specific sentence.

    Pure function.

    Args:
        doc: UnifiedDocument
        sent_idx: Sentence index

    Returns:
        Morphological statistics for sentence
    """
    if sent_idx >= len(doc.sentences):
        return {}

    sentence = doc.sentences[sent_idx]
    tokens = sentence.tokens

    return {
        "sentence_text": sentence.text,
        "token_count": len(tokens),
        "unique_lemmas": len(set(t.lemma for t in tokens)),
        "pos_distribution": get_pos_distribution(tokens),
        "pos_by_group": group_by_pos(tokens),
    }


# ============================================================================
# Feature-specific searches
# ============================================================================

def find_tokens_with_feature(
    doc: UnifiedDocument,
    feature: str,
    value: str
) -> List[UnifiedToken]:
    """
    Find all tokens with specific morphological feature value.

    Pure function.

    Args:
        doc: UnifiedDocument
        feature: Feature name (e.g., "Tense")
        value: Feature value (e.g., "Past")

    Returns:
        Matching tokens
    """
    all_tokens = [t for sent in doc.sentences for t in sent.tokens]
    return find_tokens_by_morph(all_tokens, feature, value)


def get_pos_tag_statistics(doc: UnifiedDocument) -> Dict[str, Dict[str, any]]:
    """
    Get detailed statistics for each POS tag.

    Pure function.

    Args:
        doc: UnifiedDocument

    Returns:
        Dictionary mapping POS tags to statistics
    """
    all_tokens = [t for sent in doc.sentences for t in sent.tokens]
    pos_groups = group_by_pos(all_tokens)

    statistics = {}
    for pos_tag, tokens in pos_groups.items():
        statistics[pos_tag] = {
            "count": len(tokens),
            "lemmas": list(set(t.lemma for t in tokens)),
            "sample_lemmas": list(set(t.lemma for t in tokens[:5])),
        }

    return statistics


def get_morphology_patterns(
    doc: UnifiedDocument
) -> Dict[str, int]:
    """
    Get most common morphological patterns.

    Pure function - identifies frequent combinations of features.

    Args:
        doc: UnifiedDocument

    Returns:
        Dictionary mapping morphological patterns to frequencies
    """
    all_tokens = [t for sent in doc.sentences for t in sent.tokens]

    # Create pattern strings (sorted features)
    patterns = []
    for token in all_tokens:
        if token.morph:
            pattern = ";".join(
                f"{k}={v}" for k, v in sorted(token.morph.items())
            )
            patterns.append(pattern)

    counter = Counter(patterns)
    return dict(counter)


# ============================================================================
# Comparison functions
# ============================================================================

def compare_sentences_morphology(
    doc: UnifiedDocument,
    sent_idx1: int,
    sent_idx2: int
) -> Dict[str, any]:
    """
    Compare morphological features of two sentences.

    Pure function.

    Args:
        doc: UnifiedDocument
        sent_idx1: First sentence index
        sent_idx2: Second sentence index

    Returns:
        Comparison data
    """
    if sent_idx1 >= len(doc.sentences) or sent_idx2 >= len(doc.sentences):
        return {}

    sent1 = doc.sentences[sent_idx1]
    sent2 = doc.sentences[sent_idx2]

    pos1 = get_pos_distribution(sent1.tokens)
    pos2 = get_pos_distribution(sent2.tokens)

    return {
        "sentence1_text": sent1.text,
        "sentence2_text": sent2.text,
        "sentence1_pos": pos1,
        "sentence2_pos": pos2,
        "common_pos_tags": set(pos1.keys()) & set(pos2.keys()),
        "unique_pos_in_1": set(pos1.keys()) - set(pos2.keys()),
        "unique_pos_in_2": set(pos2.keys()) - set(pos1.keys()),
    }

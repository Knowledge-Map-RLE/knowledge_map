"""
Syntactic analysis functions.

Pure functions for analyzing syntactic structures.
"""

from typing import Dict, List, Optional, Tuple, Any

from ..types import UnifiedDocument, UnifiedSentence, UnifiedToken
from ..transforms.dependency_ops import (
    find_dependencies_by_relation,
    extract_subtree,
    get_dependents,
    find_subject,
    find_objects,
    get_relation_distribution,
    build_dependency_tree_from_sentence,
)


# ============================================================================
# Document-level syntax statistics
# ============================================================================

def get_document_syntax_statistics(doc: UnifiedDocument) -> Dict[str, Any]:
    """
    Get comprehensive syntactic statistics for document.

    Pure function.

    Args:
        doc: UnifiedDocument

    Returns:
        Dictionary with syntax statistics
    """
    all_deps = [d for sent in doc.sentences for d in sent.dependencies]

    return {
        "total_sentences": len(doc.sentences),
        "total_dependencies": len(all_deps),
        "total_entities": sum(len(sent.entities) for sent in doc.sentences),
        "total_phrases": sum(len(sent.phrases) for sent in doc.sentences),
        "dependency_relations": get_relation_distribution(all_deps),
        "sentences_with_root": sum(
            1 for sent in doc.sentences if sent.root_idx is not None
        ),
    }


def get_document_entity_statistics(doc: UnifiedDocument) -> Dict[str, Any]:
    """
    Get entity distribution statistics across document.

    Pure function.

    Args:
        doc: UnifiedDocument

    Returns:
        Entity statistics
    """
    from ..transforms.entity_ops import get_entity_type_distribution

    all_entities = sum(
        [sent.entities for sent in doc.sentences],
        []
    ) + doc.entities

    return {
        "total_entities": len(all_entities),
        "entity_type_distribution": get_entity_type_distribution(all_entities),
        "unique_entities": len(set(
            " ".join(t.text for t in e.tokens) for e in all_entities
        )),
    }


# ============================================================================
# Sentence-level syntax analysis
# ============================================================================

def analyze_sentence_syntax(
    sentence: UnifiedSentence
) -> Dict[str, Any]:
    """
    Analyze syntactic structure of a sentence.

    Pure function.

    Args:
        sentence: UnifiedSentence

    Returns:
        Detailed syntax analysis
    """
    return {
        "text": sentence.text,
        "token_count": len(sentence.tokens),
        "dependency_count": len(sentence.dependencies),
        "entity_count": len(sentence.entities),
        "phrase_count": len(sentence.phrases),
        "has_root": sentence.root_idx is not None,
        "root_token": (
            sentence.tokens[sentence.root_idx].text
            if sentence.root_idx is not None else None
        ),
        "relations": get_relation_distribution(sentence.dependencies),
    }


# ============================================================================
# Subject-Verb-Object extraction
# ============================================================================

def extract_svo_triples(
    sentence: UnifiedSentence
) -> List[Dict[str, Optional[UnifiedToken]]]:
    """
    Extract Subject-Verb-Object triples from sentence.

    Pure function - finds all SVO relations.

    Args:
        sentence: UnifiedSentence

    Returns:
        List of dictionaries with subject, verb, object
    """
    triples = []

    # Find all verbs (heads with nsubj dependents)
    verb_indices = set()
    subject_map = {}

    for dep in sentence.dependencies:
        if dep.relation in ["nsubj", "nsubjpass", "csubj"]:
            subject_map[dep.head_idx] = dep.dependent_idx
            verb_indices.add(dep.head_idx)

    # For each verb, find its objects
    for verb_idx in verb_indices:
        verb_token = next(
            (t for t in sentence.tokens if t.idx == verb_idx),
            None
        )
        subject_token = next(
            (t for t in sentence.tokens if t.idx == subject_map.get(verb_idx)),
            None
        )

        # Find objects of this verb
        objects = find_objects(sentence.dependencies, sentence)
        for obj_token in objects:
            # Check if object depends (directly or indirectly) on verb
            if _is_dependent_of(sentence.dependencies, obj_token.idx, verb_idx):
                triples.append({
                    "subject": subject_token,
                    "verb": verb_token,
                    "object": obj_token,
                })

    return triples


def _is_dependent_of(
    deps: List,
    token_idx: int,
    head_idx: int,
    max_depth: int = 10
) -> bool:
    """Helper: check if token is dependent of head (recursively)."""
    from ..transforms.dependency_ops import get_head

    for _ in range(max_depth):
        parent = get_head(deps, token_idx)
        if parent is None:
            return False
        if parent == head_idx:
            return True
        token_idx = parent

    return False


# ============================================================================
# Clause extraction
# ============================================================================

def extract_clauses(sentence: UnifiedSentence) -> List[Dict[str, Any]]:
    """
    Extract clauses from sentence.

    Pure function - identifies clause boundaries via finite verbs.

    Args:
        sentence: UnifiedSentence

    Returns:
        List of clause descriptions
    """
    clauses = []

    # Find main clause (rooted at root verb)
    if sentence.root_idx is not None:
        root_subtree = extract_subtree(
            sentence.dependencies,
            sentence.root_idx,
            include_head=True
        )
        clauses.append({
            "type": "main",
            "head_idx": sentence.root_idx,
            "head_text": sentence.tokens[sentence.root_idx].text,
            "tokens": sorted(list(root_subtree)),
        })

    # Find subordinate clauses (marked by acl, advcl)
    for dep in sentence.dependencies:
        if dep.relation in ["acl", "advcl"]:
            subtree = extract_subtree(
                sentence.dependencies,
                dep.dependent_idx,
                include_head=True
            )
            clauses.append({
                "type": "subordinate",
                "head_idx": dep.dependent_idx,
                "head_text": sentence.tokens[dep.dependent_idx].text,
                "relation_to_parent": dep.relation,
                "tokens": sorted(list(subtree)),
            })

    return clauses


# ============================================================================
# Dependency pattern analysis
# ============================================================================

def find_common_dependency_patterns(
    doc: UnifiedDocument,
    pattern_length: int = 3
) -> List[Tuple[str, int]]:
    """
    Find most common dependency patterns.

    Pure function - identifies recurring syntactic structures.

    Args:
        doc: UnifiedDocument
        pattern_length: Length of dependency chain to analyze

    Returns:
        List of (pattern, frequency) tuples
    """
    from collections import Counter

    patterns = []

    for sentence in doc.sentences:
        # Get all dependency paths of length pattern_length
        for token in sentence.tokens:
            path = _get_dependency_path(
                sentence.dependencies,
                token.idx,
                max_length=pattern_length
            )
            if len(path) == pattern_length:
                pattern = "->".join(path)
                patterns.append(pattern)

    counter = Counter(patterns)
    return counter.most_common(10)


def _get_dependency_path(
    deps: List,
    token_idx: int,
    max_length: int = 3
) -> List[str]:
    """Helper: get sequence of relations from token to root."""
    from ..transforms.dependency_ops import get_head

    path = []
    current = token_idx

    for _ in range(max_length):
        parent = get_head(deps, current)
        if parent is None:
            break

        # Find the relation
        relation = next(
            (d.relation for d in deps if d.dependent_idx == current),
            "unknown"
        )
        path.append(relation)
        current = parent

    return path[:max_length]


# ============================================================================
# Phrase analysis
# ============================================================================

def analyze_phrases(sentence: UnifiedSentence) -> Dict[str, Any]:
    """
    Analyze phrases in sentence.

    Pure function.

    Args:
        sentence: UnifiedSentence

    Returns:
        Phrase statistics and details
    """
    noun_phrases = [p for p in sentence.phrases if p.phrase_type == "NP"]
    verb_phrases = [p for p in sentence.phrases if p.phrase_type == "VP"]

    return {
        "total_phrases": len(sentence.phrases),
        "noun_phrases": len(noun_phrases),
        "verb_phrases": len(verb_phrases),
        "noun_phrase_texts": [
            " ".join(t.text for t in np.tokens) for np in noun_phrases
        ],
        "verb_phrase_texts": [
            " ".join(t.text for t in vp.tokens) for vp in verb_phrases
        ],
    }


# ============================================================================
# Projectivity analysis
# ============================================================================

def is_projective(sentence: UnifiedSentence) -> bool:
    """
    Check if sentence has projective dependency tree.

    Pure function - determines if dependencies are non-crossing.

    Args:
        sentence: UnifiedSentence

    Returns:
        True if tree is projective (no crossing arcs)
    """
    from ..transforms.dependency_ops import count_crossing_arcs

    return count_crossing_arcs(sentence.dependencies) == 0


def get_projectivity_analysis(doc: UnifiedDocument) -> Dict[str, Any]:
    """
    Analyze projectivity across document.

    Pure function.

    Args:
        doc: UnifiedDocument

    Returns:
        Projectivity statistics
    """
    return {
        "total_sentences": len(doc.sentences),
        "projective_sentences": sum(
            1 for sent in doc.sentences if is_projective(sent)
        ),
        "non_projective_sentences": sum(
            1 for sent in doc.sentences if not is_projective(sent)
        ),
    }

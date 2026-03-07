"""
Pure functions for entity operations.

All functions work with named entities and are purely functional.
"""

from typing import List, Dict, Set, Tuple, Optional
from collections import defaultdict

from ..unified_types import UnifiedEntity, UnifiedToken, SCIENTIFIC_ENTITY_TYPES


# ============================================================================
# Entity filtering functions
# ============================================================================

def filter_entities_by_type(
    entities: List[UnifiedEntity],
    entity_types: Set[str]
) -> List[UnifiedEntity]:
    """
    Filter entities by type.

    Pure function.

    Args:
        entities: List of entities
        entity_types: Set of entity types to keep

    Returns:
        Entities matching specified types
    """
    return [e for e in entities if e.entity_type in entity_types]


def filter_scientific_entities(
    entities: List[UnifiedEntity]
) -> List[UnifiedEntity]:
    """
    Filter to keep only scientific entities.

    Pure function.

    Args:
        entities: List of entities

    Returns:
        Only scientific entities
    """
    return [e for e in entities if e.is_scientific]


def filter_entities_by_confidence(
    entities: List[UnifiedEntity],
    min_confidence: float
) -> List[UnifiedEntity]:
    """
    Filter entities by confidence threshold.

    Pure function.

    Args:
        entities: List of entities
        min_confidence: Minimum confidence score

    Returns:
        Entities meeting threshold
    """
    return [e for e in entities if e.confidence >= min_confidence]


def filter_overlapping_entities(
    entities: List[UnifiedEntity],
    keep_highest_confidence: bool = True
) -> List[UnifiedEntity]:
    """
    Remove overlapping entities.

    Pure function - removes lower confidence entities when they overlap.

    Args:
        entities: List of entities
        keep_highest_confidence: If True, keep highest confidence entity (default: True)

    Returns:
        Non-overlapping entities
    """
    if not entities:
        return []

    # Sort by confidence (descending) if keeping highest confidence
    if keep_highest_confidence:
        sorted_entities = sorted(entities, key=lambda e: e.confidence, reverse=True)
    else:
        sorted_entities = entities

    result = []
    for entity in sorted_entities:
        # Check if this entity overlaps with any in result
        overlaps = False
        for existing in result:
            if _spans_overlap(
                entity.start_idx, entity.end_idx,
                existing.start_idx, existing.end_idx
            ):
                overlaps = True
                break

        if not overlaps:
            result.append(entity)

    return result


def _spans_overlap(start1: int, end1: int, start2: int, end2: int) -> bool:
    """Check if two spans overlap."""
    return not (end1 <= start2 or end2 <= start1)


# ============================================================================
# Entity grouping and statistics functions
# ============================================================================

def group_entities_by_type(
    entities: List[UnifiedEntity]
) -> Dict[str, List[UnifiedEntity]]:
    """
    Group entities by type.

    Pure function.

    Args:
        entities: List of entities

    Returns:
        Dictionary mapping entity types to lists of entities
    """
    groups: Dict[str, List[UnifiedEntity]] = defaultdict(list)
    for entity in entities:
        groups[entity.entity_type].append(entity)
    return dict(groups)


def get_entity_type_distribution(
    entities: List[UnifiedEntity]
) -> Dict[str, int]:
    """
    Get frequency of each entity type.

    Pure function.

    Args:
        entities: List of entities

    Returns:
        Dictionary mapping entity types to counts
    """
    distribution: Dict[str, int] = {}
    for entity in entities:
        entity_type = entity.entity_type
        distribution[entity_type] = distribution.get(entity_type, 0) + 1
    return distribution


def get_entity_texts(entities: List[UnifiedEntity]) -> List[str]:
    """
    Extract text from entities.

    Pure function.

    Args:
        entities: List of entities

    Returns:
        List of entity texts
    """
    return [
        " ".join(t.text for t in entity.tokens)
        for entity in entities
    ]


def get_unique_entities(
    entities: List[UnifiedEntity]
) -> List[UnifiedEntity]:
    """
    Remove duplicate entities (same text and type).

    Pure function.

    Args:
        entities: List of entities

    Returns:
        Unique entities (first occurrence kept)
    """
    seen = set()
    result = []

    for entity in entities:
        # Create a key from entity text and type
        entity_text = " ".join(t.text for t in entity.tokens)
        key = (entity_text, entity.entity_type)

        if key not in seen:
            seen.add(key)
            result.append(entity)

    return result


# ============================================================================
# Entity search and lookup functions
# ============================================================================

def find_entities_by_text(
    entities: List[UnifiedEntity],
    text: str
) -> List[UnifiedEntity]:
    """
    Find entities matching text (case-sensitive).

    Pure function.

    Args:
        entities: List of entities
        text: Text to search for

    Returns:
        Matching entities
    """
    results = []
    for entity in entities:
        entity_text = " ".join(t.text for t in entity.tokens)
        if entity_text == text:
            results.append(entity)
    return results


def find_entities_by_type_and_token(
    entities: List[UnifiedEntity],
    entity_type: str,
    contains_text: str
) -> List[UnifiedEntity]:
    """
    Find entities of specific type containing specific token text.

    Pure function.

    Args:
        entities: List of entities
        entity_type: Entity type to match
        contains_text: Text that must appear in entity

    Returns:
        Matching entities
    """
    results = []
    for entity in entities:
        if entity.entity_type == entity_type:
            entity_tokens = {t.text for t in entity.tokens}
            if contains_text in entity_tokens:
                results.append(entity)
    return results


def find_entities_spanning_indices(
    entities: List[UnifiedEntity],
    start_idx: int,
    end_idx: int
) -> List[UnifiedEntity]:
    """
    Find entities overlapping with a span.

    Pure function.

    Args:
        entities: List of entities
        start_idx: Span start (inclusive)
        end_idx: Span end (exclusive)

    Returns:
        Entities overlapping the span
    """
    return [
        e for e in entities
        if _spans_overlap(start_idx, end_idx, e.start_idx, e.end_idx)
    ]


# ============================================================================
# Entity linking and resolution functions
# ============================================================================

def get_canonical_names(
    entities: List[UnifiedEntity]
) -> Dict[str, Optional[str]]:
    """
    Map entity text to canonical names.

    Pure function.

    Args:
        entities: List of entities

    Returns:
        Dictionary mapping entity text to canonical name
    """
    mapping = {}
    for entity in entities:
        entity_text = " ".join(t.text for t in entity.tokens)
        if entity.canonical_name:
            mapping[entity_text] = entity.canonical_name
    return mapping


def get_entity_ids(
    entities: List[UnifiedEntity]
) -> Dict[str, Optional[str]]:
    """
    Map entity text to knowledge base IDs.

    Pure function.

    Args:
        entities: List of entities

    Returns:
        Dictionary mapping entity text to KB ID
    """
    mapping = {}
    for entity in entities:
        entity_text = " ".join(t.text for t in entity.tokens)
        if entity.entity_id:
            mapping[entity_text] = entity.entity_id
    return mapping


# ============================================================================
# Domain filtering functions
# ============================================================================

def filter_entities_by_domain(
    entities: List[UnifiedEntity],
    domain: str
) -> List[UnifiedEntity]:
    """
    Filter scientific entities by domain.

    Pure function.

    Args:
        entities: List of entities
        domain: Domain name (e.g., "biology", "chemistry")

    Returns:
        Entities in specified domain
    """
    return [
        e for e in entities
        if e.is_scientific and e.domain == domain
    ]


def get_domain_distribution(
    entities: List[UnifiedEntity]
) -> Dict[str, int]:
    """
    Get frequency of each scientific domain.

    Pure function.

    Args:
        entities: List of entities

    Returns:
        Dictionary mapping domains to counts
    """
    distribution: Dict[str, int] = {}
    for entity in entities:
        if entity.is_scientific and entity.domain:
            distribution[entity.domain] = distribution.get(entity.domain, 0) + 1
    return distribution


# ============================================================================
# Entity span manipulation functions
# ============================================================================

def extend_entity_span(
    entity: UnifiedEntity,
    new_start_idx: int,
    new_end_idx: int,
    tokens: List[UnifiedToken]
) -> UnifiedEntity:
    """
    Extend entity span and update tokens.

    Pure function - creates new entity with extended span.

    Args:
        entity: Original entity
        new_start_idx: New start index (inclusive)
        new_end_idx: New end index (exclusive)
        tokens: All tokens in sentence

    Returns:
        New entity with extended span
    """
    new_tokens = [
        t for t in tokens
        if new_start_idx <= t.idx < new_end_idx
    ]

    return UnifiedEntity(
        entity_type=entity.entity_type,
        start_idx=new_start_idx,
        end_idx=new_end_idx,
        tokens=new_tokens,
        confidence=entity.confidence,
        sources=entity.sources,
        entity_id=entity.entity_id,
        canonical_name=entity.canonical_name,
        is_scientific=entity.is_scientific,
        domain=entity.domain,
    )


def merge_adjacent_entities(
    entities: List[UnifiedEntity]
) -> List[UnifiedEntity]:
    """
    Merge adjacent entities of the same type.

    Pure function - assumes entities are sorted by start_idx.

    Args:
        entities: List of entities

    Returns:
        Merged entities
    """
    if not entities:
        return []

    # Sort by start_idx
    sorted_entities = sorted(entities, key=lambda e: e.start_idx)

    result = []
    current = sorted_entities[0]

    for next_entity in sorted_entities[1:]:
        # Check if adjacent and same type
        if (current.end_idx == next_entity.start_idx and
            current.entity_type == next_entity.entity_type):
            # Merge
            merged_tokens = current.tokens + next_entity.tokens
            current = UnifiedEntity(
                entity_type=current.entity_type,
                start_idx=current.start_idx,
                end_idx=next_entity.end_idx,
                tokens=merged_tokens,
                confidence=(current.confidence + next_entity.confidence) / 2,
                sources=list(set(current.sources + next_entity.sources)),
                entity_id=current.entity_id or next_entity.entity_id,
                canonical_name=current.canonical_name or next_entity.canonical_name,
                is_scientific=current.is_scientific or next_entity.is_scientific,
                domain=current.domain or next_entity.domain,
            )
        else:
            # Not adjacent, add current to result
            result.append(current)
            current = next_entity

    result.append(current)
    return result

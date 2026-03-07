"""
Pure functions for dependency parsing operations.

All functions in this module are pure and work with dependency structures.
"""

from typing import List, Dict, Set, Tuple, Optional

import networkx as nx

from ..unified_types import UnifiedDependency, UnifiedSentence, UnifiedToken


# ============================================================================
# Graph construction functions
# ============================================================================

def build_dependency_tree(
    deps: List[UnifiedDependency],
    num_tokens: int | None = None
) -> nx.DiGraph:
    """
    Build a directed dependency graph.

    Pure function - creates graph from dependency list.

    Args:
        deps: List of dependency relations
        num_tokens: Total number of tokens (optional, for validation)

    Returns:
        NetworkX directed graph where edge (head, dependent) has 'relation' attribute
    """
    graph = nx.DiGraph()

    # Add all tokens as nodes
    if num_tokens:
        for i in range(num_tokens):
            graph.add_node(i)

    # Add dependency edges
    for dep in deps:
        graph.add_edge(
            dep.head_idx,
            dep.dependent_idx,
            relation=dep.relation,
            confidence=dep.confidence
        )

    return graph


def build_dependency_tree_from_sentence(
    sentence: UnifiedSentence
) -> nx.DiGraph:
    """
    Build a dependency tree from a UnifiedSentence.

    Pure convenience function.

    Args:
        sentence: Complete sentence with dependencies

    Returns:
        NetworkX directed graph
    """
    return build_dependency_tree(sentence.dependencies, len(sentence.tokens))


# ============================================================================
# Root and head finding functions
# ============================================================================

def find_root(deps: List[UnifiedDependency]) -> Optional[int]:
    """
    Find the root token (head with no parent).

    Pure function.

    Args:
        deps: List of dependency relations

    Returns:
        Index of root token, or None if no root found
    """
    # Root is the token that never appears as dependent
    heads = {dep.head_idx for dep in deps}
    dependents = {dep.dependent_idx for dep in deps}

    # Root is head that's not a dependent
    roots = heads - dependents
    return next(iter(roots), None) if roots else None


def get_head(
    deps: List[UnifiedDependency],
    token_idx: int
) -> Optional[int]:
    """
    Get the head of a token.

    Pure function.

    Args:
        deps: List of dependencies
        token_idx: Token index

    Returns:
        Head token index, or None if token has no head
    """
    for dep in deps:
        if dep.dependent_idx == token_idx:
            return dep.head_idx
    return None


def get_dependents(
    deps: List[UnifiedDependency],
    head_idx: int
) -> List[Tuple[int, str]]:
    """
    Get all direct dependents of a token.

    Pure function.

    Args:
        deps: List of dependencies
        head_idx: Head token index

    Returns:
        List of (dependent_idx, relation) tuples
    """
    return [
        (dep.dependent_idx, dep.relation)
        for dep in deps
        if dep.head_idx == head_idx
    ]


# ============================================================================
# Subtree extraction functions
# ============================================================================

def extract_subtree(
    deps: List[UnifiedDependency],
    head_idx: int,
    include_head: bool = True
) -> Set[int]:
    """
    Extract all tokens in subtree rooted at head.

    Pure recursive function (using memoization approach).

    Args:
        deps: List of dependencies
        head_idx: Root of subtree
        include_head: Whether to include head in result (default: True)

    Returns:
        Set of token indices in subtree
    """
    result = set()
    if include_head:
        result.add(head_idx)

    # Add all direct dependents and their subtrees
    for dependent_idx, _ in get_dependents(deps, head_idx):
        result.update(extract_subtree(deps, dependent_idx, include_head=True))

    return result


def get_path_to_root(
    deps: List[UnifiedDependency],
    token_idx: int,
    max_depth: int = 100
) -> List[int]:
    """
    Get path from token to root.

    Pure function - traces up dependency tree.

    Args:
        deps: List of dependencies
        token_idx: Starting token
        max_depth: Maximum path length (prevent infinite loops)

    Returns:
        List of indices from token to root (inclusive)
    """
    path = [token_idx]
    current = token_idx

    for _ in range(max_depth):
        head = get_head(deps, current)
        if head is None or head == current:
            # Reached root or cycle
            break
        path.append(head)
        current = head

    return path


def find_lowest_common_ancestor(
    deps: List[UnifiedDependency],
    token_idx1: int,
    token_idx2: int
) -> Optional[int]:
    """
    Find lowest common ancestor of two tokens.

    Pure function - finds LCA in dependency tree.

    Args:
        deps: List of dependencies
        token_idx1: First token
        token_idx2: Second token

    Returns:
        LCA index, or None if not found
    """
    path1 = set(get_path_to_root(deps, token_idx1))
    path2 = get_path_to_root(deps, token_idx2)

    for ancestor in path2:
        if ancestor in path1:
            return ancestor

    return None


# ============================================================================
# Relation and pattern searching functions
# ============================================================================

def find_dependencies_by_relation(
    deps: List[UnifiedDependency],
    relation: str
) -> List[UnifiedDependency]:
    """
    Find all dependencies of a specific relation type.

    Pure function.

    Args:
        deps: List of dependencies
        relation: Relation type to search (e.g., "nsubj")

    Returns:
        Matching dependencies
    """
    return [d for d in deps if d.relation == relation]


def find_subject(
    deps: List[UnifiedDependency],
    sentence: UnifiedSentence
) -> Optional[UnifiedToken]:
    """
    Find subject token (nsubj relation).

    Pure function.

    Args:
        deps: List of dependencies
        sentence: Complete sentence (for token lookup)

    Returns:
        Subject token, or None if not found
    """
    for dep in deps:
        if dep.relation in ["nsubj", "nsubjpass", "csubj"]:
            return next(
                (t for t in sentence.tokens if t.idx == dep.dependent_idx),
                None
            )
    return None


def find_objects(
    deps: List[UnifiedDependency],
    sentence: UnifiedSentence
) -> List[UnifiedToken]:
    """
    Find object tokens (obj, iobj relations).

    Pure function.

    Args:
        deps: List of dependencies
        sentence: Complete sentence

    Returns:
        List of object tokens
    """
    objects = []
    for dep in deps:
        if dep.relation in ["obj", "iobj", "obl"]:
            token = next(
                (t for t in sentence.tokens if t.idx == dep.dependent_idx),
                None
            )
            if token:
                objects.append(token)
    return objects


def find_prepositional_phrases(
    deps: List[UnifiedDependency],
    sentence: UnifiedSentence
) -> List[Tuple[int, int]]:
    """
    Find prepositional phrases (marked by case relation).

    Pure function - returns spans of PP.

    Args:
        deps: List of dependencies
        sentence: Complete sentence

    Returns:
        List of (start_idx, end_idx) spans for each PP
    """
    phrases = []

    # Find all prepositions (case relations)
    for dep in deps:
        if dep.relation == "case":
            # PP starts at preposition, extends through its dependents
            pp_tokens = extract_subtree(deps, dep.dependent_idx, include_head=True)
            if pp_tokens:
                start = min(pp_tokens)
                end = max(pp_tokens) + 1
                phrases.append((start, end))

    return phrases


# ============================================================================
# Relation counting and statistics functions
# ============================================================================

def get_relation_distribution(
    deps: List[UnifiedDependency]
) -> Dict[str, int]:
    """
    Get frequency of each dependency relation type.

    Pure function.

    Args:
        deps: List of dependencies

    Returns:
        Dictionary mapping relation types to counts
    """
    distribution: Dict[str, int] = {}
    for dep in deps:
        distribution[dep.relation] = distribution.get(dep.relation, 0) + 1
    return distribution


def get_average_dependency_length(
    deps: List[UnifiedDependency]
) -> float:
    """
    Calculate average distance between head and dependent.

    Pure function.

    Args:
        deps: List of dependencies

    Returns:
        Mean distance between tokens in dependency relations
    """
    if not deps:
        return 0.0

    distances = [
        abs(dep.head_idx - dep.dependent_idx)
        for dep in deps
    ]
    return sum(distances) / len(distances)


def count_arcs(deps: List[UnifiedDependency]) -> int:
    """
    Count number of dependency arcs.

    Pure function.

    Args:
        deps: List of dependencies

    Returns:
        Number of dependencies
    """
    return len(deps)


def count_crossing_arcs(deps: List[UnifiedDependency]) -> int:
    """
    Count number of crossing (non-projective) dependency arcs.

    Pure function.

    Args:
        deps: List of dependencies

    Returns:
        Count of crossing arcs
    """
    crossing = 0

    for i, dep1 in enumerate(deps):
        for dep2 in deps[i+1:]:
            # Check if arcs cross
            # They cross if: a < c < b < d where arc1 is (a,b) and arc2 is (c,d)
            a, b = min(dep1.head_idx, dep1.dependent_idx), max(dep1.head_idx, dep1.dependent_idx)
            c, d = min(dep2.head_idx, dep2.dependent_idx), max(dep2.head_idx, dep2.dependent_idx)

            if a < c < b < d or c < a < d < b:
                crossing += 1

    return crossing


# ============================================================================
# Modification functions
# ============================================================================

def filter_dependencies_by_confidence(
    deps: List[UnifiedDependency],
    min_confidence: float
) -> List[UnifiedDependency]:
    """
    Filter dependencies by confidence threshold.

    Pure function.

    Args:
        deps: List of dependencies
        min_confidence: Minimum confidence score

    Returns:
        Dependencies meeting threshold
    """
    return [d for d in deps if d.confidence >= min_confidence]


def reindex_dependencies(
    deps: List[UnifiedDependency],
    offset: int
) -> List[UnifiedDependency]:
    """
    Shift all token indices by offset.

    Pure function - useful for combining multiple sentences.

    Args:
        deps: List of dependencies
        offset: Index offset to add

    Returns:
        Dependencies with adjusted indices
    """
    return [
        UnifiedDependency(
            head_idx=dep.head_idx + offset,
            dependent_idx=dep.dependent_idx + offset,
            relation=dep.relation,
            confidence=dep.confidence,
            sources=dep.sources,
            metadata=dep.metadata,
        )
        for dep in deps
    ]

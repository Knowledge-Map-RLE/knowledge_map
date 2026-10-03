"""Deterministic quality metrics for Article → structural rows → Knowledge Map.

The module deliberately does not call an LLM. It reports verifiable properties
of a completed Variant A transformation and explicitly labels properties which
need an expert or a future gold-standard comparison.
"""
from __future__ import annotations

import re
from collections import Counter, deque
from typing import Any

from knowledge_contracts.block_types import BlockType
from knowledge_contracts.block_dsl import REF_FIELDS, REFS_FIELDS, REF_GROUPS_FIELDS
from knowledge_contracts.validation import (ValidationError, validate_linguistic,
                                            validate_map, validate_structural)
from .caption_units import caption_unit_ids


QUALITY_METRICS_VERSION = 6


_EVIDENCE_NON_TEXT_KEYS = {"tag", "unit", "source", "provenance", "subjectOperation"}
_REF_TAG_RE = re.compile(r"^[bB][0-9]+$")
_TERM_RE = re.compile(r"[a-zа-яёöüä]{2,}")
_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "of", "in", "on", "at", "to", "for",
    "with", "by", "from", "as", "into", "that", "which", "this", "those", "these",
    "it", "its", "we", "they", "their", "our", "is", "are", "was", "were", "be",
    "been", "being", "not", "no", "vs", "via", "than", "over", "under", "also",
    "only", "however", "thus", "therefore", "one", "two", "while", "when", "where",
}


def _evidence_check(source, profile, blocks):
    """Word-overlap evidence: the terms a row asserts must occur in its sentence.

    Deterministic token-overlap heuristic (lemma-agnostic, lowercase term match)
    for automated semantic-fidelity accounting. Deliberately shallow: absence of
    overlap does not prove a false assertion, so the aggregate is reported as a
    metric and not a gate.
    """
    sentences = profile.get("sentences", [])
    sentence_lemmas: dict[str, set[str]] = {}
    for token in profile.get("tokens", []):
        lemma = str(token.get("lemma") or token.get("text") or "").lower()
        if lemma:
            sentence_lemmas.setdefault(token.get("sentence_id"), set()).add(lemma)
    details = []
    supported = 0
    for block in blocks:
        data = block.get("data", {})
        provenance = data.get("provenance", {})
        unit_ids = provenance.get("unit_ids", [])
        index = None
        for unit in unit_ids:
            match = re.match(r"^S([1-9][0-9]*)$", str(unit))
            if match:
                index = int(match.group(1)) - 1
                break
        sentence_id = sentences[index]["id"] if index is not None and 0 <= index < len(sentences) else None
        terms: set[str] = set()
        for key, value in data.items():
            if (key in _EVIDENCE_NON_TEXT_KEYS or key in REF_FIELDS
                    or key in REFS_FIELDS or key in REF_GROUPS_FIELDS
                    or not isinstance(value, (str, list))):
                continue
            values = value if isinstance(value, list) else [value]
            for item in values:
                if not isinstance(item, str) or _REF_TAG_RE.match(item):
                    continue
                terms.update(t for t in _TERM_RE.findall(item.lower()) if t not in _STOPWORDS)
        if not terms:
            details.append({"instanceId": block.get("instanceId"), "unit": unit_ids,
                            "term_count": 0, "matched": 0, "fraction": 1.0, "supported": True})
            supported += 1
            continue
        lemmas = sentence_lemmas.get(sentence_id, set()) if sentence_id else set()
        matched = sum(1 for term in terms if term in lemmas)
        fraction = matched / len(terms)
        is_supported = fraction >= 0.5
        if is_supported:
            supported += 1
        details.append({"instanceId": block.get("instanceId"), "unit": unit_ids,
                        "term_count": len(terms), "matched": matched,
                        "fraction": round(fraction, 6), "supported": is_supported})
    total = len(blocks)
    return {
        "blocks_supported": supported,
        "blocks_total": total,
        "evidence_fraction": _ratio(supported, total),
        "details": details,
    }


def _ratio(numerator: float, denominator: float) -> float:
    return round(numerator / denominator, 6) if denominator else 1.0


def _is_source_span(span: object, source: dict[str, Any]) -> bool:
    return (
        isinstance(span, dict)
        and span.get("revision_id") == source.get("id")
        and isinstance(span.get("start"), int)
        and isinstance(span.get("end"), int)
        and 0 <= span["start"] < span["end"] <= len(source.get("text", ""))
    )


def _components(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> int:
    """Count weakly connected components without requiring a graph library."""
    adjacency: dict[str, set[str]] = {node["id"]: set() for node in nodes}
    for edge in edges:
        source, target = edge.get("source"), edge.get("target")
        if source in adjacency and target in adjacency:
            adjacency[source].add(target)
            adjacency[target].add(source)
    visited: set[str] = set()
    count = 0
    for identifier in adjacency:
        if identifier in visited:
            continue
        count += 1
        queue = deque([identifier])
        visited.add(identifier)
        while queue:
            current = queue.popleft()
            for neighbour in adjacency[current]:
                if neighbour not in visited:
                    visited.add(neighbour)
                    queue.append(neighbour)
    return count


def _schema_gates(source: dict[str, Any], profile: dict[str, Any],
                  blocks: list[dict[str, Any]], graph: dict[str, Any]) -> dict[str, bool]:
    sentence_by_id = {s["id"]: s for s in profile.get("sentences", [])}
    ordered_sentences = [sentence_by_id[sid] for sid in sentence_by_id]
    gates = {
        "linguistic_schema_valid": False,
        "structural_schema_valid": False,
        "knowledge_map_schema_valid": False,
    }
    try:
        validate_linguistic(profile, source)
        gates["linguistic_schema_valid"] = True
    except ValidationError:
        pass
    try:
        validate_structural(blocks, source, ordered_sentences)
        gates["structural_schema_valid"] = True
    except ValidationError:
        pass
    try:
        validate_map(graph, blocks)
        gates["knowledge_map_schema_valid"] = True
    except ValidationError:
        pass
    return gates


def _fingerprint(block: dict[str, Any]) -> tuple[Any, ...]:
    data = block["data"]
    excluded = {"tag", "unit", "source", "provenance"}
    items = tuple(sorted((key, repr(value)) for key, value in data.items() if key not in excluded))
    return block["blockType"], items


def evaluate_article_transformation(
    source: dict[str, Any],
    profile: dict[str, Any],
    blocks: list[dict[str, Any]],
    graph: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate one completed Variant A transformation without semantic claims.

    Returned values are JSON serialisable and stable enough to be persisted in a
    checkpoint. ``manual_review`` holds metrics which cannot be inferred safely
    from the map alone.
    """
    schema = _schema_gates(source, profile, blocks, graph)
    evidence = _evidence_check(source, profile, blocks)
    text = source.get("text", "")
    tokens = profile.get("tokens", [])
    sentences = profile.get("sentences", [])

    valid_provenance_blocks = 0
    represented_token_ids: set[Any] = set()
    for block in blocks:
        spans = block.get("data", {}).get("provenance", {}).get("source_spans", [])
        if spans and all(_is_source_span(span, source) for span in spans):
            valid_provenance_blocks += 1
            for span in spans:
                represented_token_ids.update(
                    token["id"] for token in tokens
                    if token["start"] < span["end"] and token["end"] > span["start"])
    span_pairs = [(span["start"], span["end"])
                  for block in blocks for span in block.get("data", {}).get("provenance", {}).get("source_spans", [])]
    sentence_coverage = sum(
        any(s_start < sentence["end"] and s_end > sentence["start"] for s_start, s_end in span_pairs)
        for sentence in sentences
    )

    relation_rows = [block for block in blocks
                     if block["blockType"] in (BlockType.RELATION, BlockType.TEMPORAL_RELATION)]
    edges = graph.get("edges", [])
    graph_nodes = graph.get("nodes", [])
    node_ids = {node["id"] for node in graph_nodes}
    resolvable_edges = [edge for edge in edges
                        if edge["source"] in node_ids and edge["target"] in node_ids]
    degree = Counter(item for edge in resolvable_edges for item in (edge["source"], edge["target"]))
    orphan_nodes = [node["id"] for node in graph_nodes if node["id"] not in degree]

    typed_block_counts = Counter(block.get("blockType") for block in blocks)
    statement_like = [block for block in blocks
                      if block["blockType"] in (BlockType.STATEMENT, BlockType.CLAIM,
                                                BlockType.ENTITY, BlockType.ACTION)]
    duplicate_candidates = sum(count - 1
                               for count in Counter(map(_fingerprint, blocks)).values() if count > 1)
    caption_units = caption_unit_ids(profile, text)
    caption_rows = [block for block in blocks
                    if caption_units.intersection(
                        block.get("data", {}).get("provenance", {}).get("unit_ids", []) or [])]
    caption_image_units = {
        unit for block in caption_rows if block.get("blockType") == BlockType.IMAGE
        for unit in block.get("data", {}).get("provenance", {}).get("unit_ids", []) or []
        if unit in caption_units
    }
    caption_semantic_rows = [block for block in caption_rows
                             if block.get("blockType") not in (BlockType.IMAGE, BlockType.METADATA)]
    uncovered_caption_units = sorted(caption_units - caption_image_units,
                                     key=lambda unit: int(unit[1:]))

    gates = {
        **schema,
        "source_provenance_complete": valid_provenance_blocks == len(blocks),
        "source_not_empty": bool(text.strip()),
        "caption_conversion_complete": not uncovered_caption_units,
    }
    gate_passed = all(gates.values())

    automated_components = {
        "structural_integrity": 1.0 if all(schema.values()) else 0.0,
        "provenance": _ratio(valid_provenance_blocks, len(blocks)),
        "semantic_coverage": _ratio(len(represented_token_ids), len(tokens)),
        "edge_resolution": _ratio(len(resolvable_edges), len(edges)),
        "graph_health": (
            _ratio(len(resolvable_edges), len(edges)) +
            (1.0 - _ratio(len(orphan_nodes), len(graph_nodes)))
        ) / 2,
    }
    weights = {"structural_integrity": 0.20, "provenance": 0.20, "semantic_coverage": 0.20,
               "edge_resolution": 0.20, "graph_health": 0.20}
    automated_score = round(100 * sum(automated_components[key] * weights[key] for key in weights), 2)

    return {
        "version": QUALITY_METRICS_VERSION,
        "gates": {"passed": gate_passed, "checks": gates},
        "linguistic": {
            "sentence_count": len(sentences),
            "token_count": len(tokens),
            "section_count": len(profile.get("sections", [])),
            "dependency_count": len(profile.get("dependencies", [])),
            "phrase_count": len(profile.get("phrases", [])),
            "source_sentence_coverage": _ratio(sentence_coverage, len(sentences)),
            "semantic_token_fraction": _ratio(len(represented_token_ids), len(tokens)),
        },
        "structural_rows": {
            "row_count": len(blocks),
            "block_types": dict(sorted(typed_block_counts.items())),
            "statement_count": len(statement_like),
            "relation_row_count": len(relation_rows),
            "caption_row_count": len(caption_rows),
            "caption_image_row_count": sum(
                block.get("blockType") == BlockType.IMAGE for block in caption_rows),
            "caption_semantic_row_count": len(caption_semantic_rows),
            "provenance_completeness": _ratio(valid_provenance_blocks, len(blocks)),
            "duplicate_fingerprint_candidates": duplicate_candidates,
        },
        "knowledge_map": {
            "node_count": len(graph_nodes),
            "edge_count": len(edges),
            "link_resolvability": _ratio(len(resolvable_edges), len(edges)),
            "orphan_node_count": len(orphan_nodes),
            "orphan_node_fraction": _ratio(len(orphan_nodes), len(graph_nodes)),
            "weakly_connected_components": _components(graph_nodes, resolvable_edges),
        },
        "source_accounting": {
            "source_not_empty": bool(text.strip()),
            "sentence_count": len(sentences),
            "covered_sentence_count": sentence_coverage,
            "uncovered_sentence_count": len(sentences) - sentence_coverage,
            "token_count": len(tokens),
            "represented_token_count": len(represented_token_ids),
            "caption_unit_count": len(caption_units),
            "caption_image_covered_unit_count": len(caption_image_units),
            "caption_image_coverage": _ratio(len(caption_image_units), len(caption_units)),
            "uncovered_caption_unit_ids": uncovered_caption_units,
        },
        "quality": {
            "automated_score": automated_score,
            "automated_components": {key: round(value, 6) for key, value in automated_components.items()},
            "semantic_fidelity": round(evidence["evidence_fraction"], 6),
        },
        "evidence": evidence,
        "manual_review": {
            "assertion_precision": "requires_gold_standard",
            "assertion_recall": "requires_gold_standard",
            "relation_f1": "requires_gold_standard",
            "context_f1": "requires_gold_standard",
            "modality_f1": "requires_gold_standard",
            "atomicity": "requires_expert_review",
            "scientific_faithfulness": "requires_expert_review",
            "absence_of_external_knowledge": "requires_expert_review",
        },
    }

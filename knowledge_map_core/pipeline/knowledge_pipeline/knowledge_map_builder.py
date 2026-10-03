"""Детерминированное построение карты знаний из структурных строк.

Структурные строки являются исходными свидетельствами, а не готовыми узлами.
Типизированные знания и действия становятся узлами по контракту; контекстные,
измерительные и relation-строки хранятся как свидетельства. Фиксированные
правила по типам, типизированным ссылкам, точным совпадениям полей и порядку
источника создают единые направленные рёбра. Построитель не использует LLM.
"""
from __future__ import annotations

import heapq
import unicodedata
from typing import Any, Dict, List, Set, Tuple

from knowledge_contracts.block_dsl import (
    DSL_FIELDS, EVIDENCE_OWNER_FIELDS, MAP_NODE_TYPES, REF_FIELDS,
    REFS_FIELDS, REF_GROUPS_FIELDS,
)
from knowledge_contracts.block_types import BlockType
from knowledge_contracts.dsl_tags import iter_tags
from knowledge_contracts.validation import require, validate_map
from .knowledge_map_rules import (
    EXACT_FIELD_TRANSITIONS, GOAL_SOURCE_FIELDS, GOAL_TARGET_FIELDS,
    ORDERED_PREDECESSORS, REFERENCE_TRANSITIONS,
)

_SKIP_FIELDS = {
    "tag", "unit", "provenance", "source", "_extra",
    "requiresRefs", "requiresAnyOfRefs",
}
def _display_text(block: Dict[str, Any]) -> str:
    block_type = block["blockType"]
    data = block["data"]
    if block_type == BlockType.RELATION:
        source, target, relation = data["source"], data["target"], data.get("relationType", "")
        text = f"{source} → {target}" if not relation else f"{source} {relation} {target}"
        if data.get("confidence"):
            text = f"{text} (confidence: {data['confidence']})"
        return text
    if block_type == BlockType.TEMPORAL_RELATION:
        return f"{data.get('earlier','')} {data.get('relationType','precedes')} {data.get('later','')}"
    parts: List[str] = []
    for key, value in data.items():
        if (key in _SKIP_FIELDS or key in REF_FIELDS or key in REFS_FIELDS
                or key in REF_GROUPS_FIELDS):
            continue
        if value in (None, "", [], {}):
            continue
        rendered = ", ".join(str(item) for item in value) if isinstance(value, list) else str(value)
        parts.append(f"{key}: {rendered}")
    return " | ".join(parts) if parts else block_type


def _normalize_exact(value: str) -> str:
    """Normalize Unicode/case/spacing while preserving words and punctuation."""
    return " ".join(unicodedata.normalize("NFKC", str(value)).casefold().split())


def _ref_tags(value: Any) -> List[str]:
    if not value:
        return []
    if isinstance(value, (list, tuple)):
        return list(dict.fromkeys(tag for item in value for tag in _ref_tags(item)))
    return iter_tags(str(value))


def _assign_ranks(nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]) -> None:
    """Assign stable longest-path ranks and reject cycles before persistence."""
    by_id = {node["id"]: node for node in nodes}
    outgoing = {identifier: [] for identifier in by_id}
    indegree = {identifier: 0 for identifier in by_id}
    for edge in edges:
        outgoing[edge["source"]].append(edge["target"])
        indegree[edge["target"]] += 1
    ready = [
        (by_id[identifier]["order"], identifier)
        for identifier, degree in indegree.items() if degree == 0
    ]
    heapq.heapify(ready)
    visited = 0
    for node in nodes:
        node["rank"] = 0
    while ready:
        _, current = heapq.heappop(ready)
        visited += 1
        for child in sorted(outgoing[current], key=lambda identifier: (by_id[identifier]["order"], identifier)):
            by_id[child]["rank"] = max(by_id[child]["rank"], by_id[current]["rank"] + 1)
            indegree[child] -= 1
            if indegree[child] == 0:
                heapq.heappush(ready, (by_id[child]["order"], child))
    if visited != len(nodes):
        blocked_rows = [node.get("tag", node["id"]) for node in nodes
                        if indegree[node["id"]] > 0]
        require(False, "Knowledge-map progression graph contains a cycle; "
                f"blocked rows: {', '.join(blocked_rows)}")


def _field_values(block: Dict[str, Any], fields: Tuple[str, ...]) -> Dict[str, List[str]]:
    values: Dict[str, List[str]] = {}
    for field in fields:
        value = block["data"].get(field)
        items = value if isinstance(value, list) else [value]
        normalized = list(dict.fromkeys(
            _normalize_exact(str(item)) for item in items
            if item not in (None, "", [], {})
        ))
        if normalized:
            values[field] = normalized
    return values


def _unique_exact_predecessors(target: Dict[str, Any], candidates: List[Dict[str, Any]]) -> List[Tuple[Dict[str, Any], str, str]]:
    """Match registered field pairs only when an exact value identifies one row."""
    field_pairs = EXACT_FIELD_TRANSITIONS.get(target["blockType"], {})
    matches: Dict[Tuple[str, str, str], Tuple[Dict[str, Any], str, str]] = {}
    for source_type, pairs in field_pairs.items():
        typed_candidates = [item for item in candidates if item["blockType"] == source_type]
        for source_field, target_field in pairs:
            target_values = _field_values(target, (target_field,)).get(target_field, [])
            for value in target_values:
                matching_rows = [candidate for candidate in typed_candidates
                                 if value in _field_values(candidate, (source_field,))
                                 .get(source_field, [])]
                if len(matching_rows) == 1:
                    source = matching_rows[0]
                    key = (source["instanceId"], target["instanceId"], target_field)
                    matches[key] = (source, source_field, target_field)
    return list(matches.values())


def build_knowledge_map(blocks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build a deterministic v3 map with untyped left-to-right route edges."""
    tags_to_instance = {
        block["data"]["tag"]: block["instanceId"]
        for block in blocks if block["data"].get("tag")
    }
    tagged_row_count = sum(bool(block["data"].get("tag")) for block in blocks)
    require(len(tags_to_instance) == tagged_row_count, "Duplicate structural row tags")
    node_tags = {block["data"]["tag"] for block in blocks
                 if block["data"].get("tag") and block["blockType"] in MAP_NODE_TYPES}

    nodes = []
    for block in blocks:
        tag = block["data"].get("tag")
        if tag not in node_tags:
            continue
        data = block["data"]
        properties = {
            key: value for key, value in data.items()
            if key not in _SKIP_FIELDS | REF_FIELDS | REFS_FIELDS | REF_GROUPS_FIELDS
            and value not in (None, "", [], {})
        }
        nodes.append({
            "id": block["instanceId"], "block_type": block["blockType"],
            "tag": tag, "order": block["order"],
            "structural_id": block["instanceId"],
            "display_text": _display_text(block), "properties": properties,
            "evidence_refs": [], "is_goal": block["blockType"] in
                (BlockType.GOAL, BlockType.IMPACT_GOAL),
        })
    node_ids = {node["id"] for node in nodes}
    edges_by_key: Dict[Tuple[str, str], Dict[str, Any]] = {}

    def add_edge(source: Dict[str, Any], target: Dict[str, Any],
                 *witnesses: Tuple[Dict[str, Any], str]) -> None:
        source_id, target_id = source["instanceId"], target["instanceId"]
        require(source_id in node_ids and target_id in node_ids,
                "Knowledge-map route endpoints must be map nodes")
        require(source_id != target_id, "Knowledge-map self-loop")
        key = (source_id, target_id)
        edge = edges_by_key.setdefault(key, {
            "source": source_id, "target": target_id, "evidence": [],
        })
        for witness_row, field in witnesses:
            witness = {"structural_id": witness_row["instanceId"], "field": field}
            if witness not in edge["evidence"]:
                edge["evidence"].append(witness)

    blocks_by_tag = {block["data"].get("tag"): block for block in blocks
                     if block["data"].get("tag")}
    # Typed references define direction explicitly and always outrank fallback order.
    explicit_pairs: Set[Tuple[str, str]] = set()
    for rule in REFERENCE_TRANSITIONS:
        for owner in blocks:
            if owner["blockType"] != rule.owner_type:
                continue
            for referenced_tag in _ref_tags(owner["data"].get(rule.field)):
                referenced = blocks_by_tag.get(referenced_tag)
                if not referenced or referenced["blockType"] not in rule.referenced_types:
                    continue
                if rule.direction == "owner_to_reference":
                    source, target = owner, referenced
                else:
                    source, target = referenced, owner
                if source["instanceId"] not in node_ids or target["instanceId"] not in node_ids:
                    continue
                add_edge(source, target, (owner, rule.field))
                explicit_pairs.add((source["instanceId"], target["instanceId"]))

    # For each allowed stage transition, registered exact field matches win.
    # If none identify a unique row, select the closest preceding allowed type.
    ordered_blocks = sorted(blocks, key=lambda item: (item["order"], item["instanceId"]))
    for target in ordered_blocks:
        allowed_types = ORDERED_PREDECESSORS.get(target["blockType"], ())
        if not allowed_types or target["instanceId"] not in node_ids:
            continue
        previous = [item for item in ordered_blocks
                    if item["order"] < target["order"]
                    and item["blockType"] in allowed_types
                    and item["instanceId"] in node_ids]
        if not previous:
            continue
        exact = _unique_exact_predecessors(target, previous)
        if exact:
            for source, source_field, target_field in exact:
                if (source["instanceId"], target["instanceId"]) not in explicit_pairs:
                    add_edge(source, target,
                             (source, source_field), (target, target_field))
            continue
        nearest = previous[-1]
        if (nearest["instanceId"], target["instanceId"]) not in explicit_pairs:
            add_edge(nearest, target,
                     (nearest, "source_order"),
                     (target, f"transition:{target['blockType']}"))

    # A method opens a local result chain. The next method or experiment closes
    # it; all findings and results inside the interval retain direct provenance.
    for index, method in enumerate(ordered_blocks):
        if method["blockType"] != BlockType.METHOD or method["instanceId"] not in node_ids:
            continue
        for candidate in ordered_blocks[index + 1:]:
            if candidate["blockType"] in (BlockType.METHOD, BlockType.EXPERIMENT):
                break
            if candidate["blockType"] in (BlockType.FINDING, BlockType.RESULT):
                add_edge(method, candidate,
                         (method, "local_method_chain"),
                         (candidate, "source_order"))

    # Goal links are order independent, but require a unique exact value match.
    goals = [block for block in ordered_blocks
             if block["blockType"] in (BlockType.GOAL, BlockType.IMPACT_GOAL)]
    for goal in goals:
        goal_values = _field_values(goal, GOAL_TARGET_FIELDS)
        target_values = {value for values in goal_values.values() for value in values}
        if not target_values:
            continue
        for source in ordered_blocks:
            if source["blockType"] not in GOAL_SOURCE_FIELDS or source["instanceId"] == goal["instanceId"]:
                continue
            source_fields = _field_values(source, GOAL_SOURCE_FIELDS[source["blockType"]])
            exact_fields = [(field, value) for field, values in source_fields.items()
                            for value in values if value in target_values]
            if not exact_fields:
                continue
            matching_sources = []
            for candidate in ordered_blocks:
                if candidate["blockType"] not in GOAL_SOURCE_FIELDS:
                    continue
                fields = _field_values(candidate, GOAL_SOURCE_FIELDS[candidate["blockType"]])
                if any(value in target_values for values in fields.values() for value in values):
                    matching_sources.append(candidate)
            if len({item["instanceId"] for item in matching_sources}) != 1:
                continue
            source_field, matched_value = exact_fields[0]
            goal_field = next(field for field, values in goal_values.items()
                              if matched_value in values)
            add_edge(source, goal, (source, source_field), (goal, goal_field))

    edges = list(edges_by_key.values())
    for edge in edges:
        edge["evidence"].sort(key=lambda item: (item["structural_id"], item["field"]))
    _assign_ranks(nodes, edges)
    nodes_by_id = {node["id"]: node for node in nodes}

    # Explicit owner fields attach context/measurement rows only when there is
    # one unambiguous node owner. Unowned evidence stays in the map payload.
    evidence_owners: Dict[str, Set[str]] = {}
    for block in blocks:
        owner_tag = block["data"].get("tag")
        if not owner_tag:
            continue
        owner_id = tags_to_instance[owner_tag]
        if owner_id not in node_ids:
            continue
        for spec in DSL_FIELDS[block["blockType"]].values():
            field = spec.json_field
            if field not in EVIDENCE_OWNER_FIELDS or spec.kind not in ("ref", "refs", "ref_groups"):
                continue
            for target_tag in _ref_tags(block["data"].get(field)):
                target_id = tags_to_instance.get(target_tag)
                if target_id and target_id not in node_ids:
                    evidence_owners.setdefault(target_id, set()).add(owner_id)

    evidence = []
    for block in sorted(blocks, key=lambda item: item["order"]):
        identifier = block["instanceId"]
        if identifier in node_ids:
            continue
        owners = evidence_owners.get(identifier, set())
        owner_id = next(iter(owners)) if len(owners) == 1 else None
        evidence.append({
            "id": identifier, "block_type": block["blockType"],
            "tag": block["data"].get("tag"), "order": block["order"],
            "owner_id": owner_id,
            "owner_resolution": "unique" if owner_id else ("ambiguous" if owners else "unattached"),
            "display_text": _display_text(block),
        })
        if owner_id:
            nodes_by_id[owner_id]["evidence_refs"].append(identifier)

    graph = {
        "schema_version": 3,
        "nodes": nodes,
        "edges": edges,
        "evidence": evidence,
        "reading_order": [block["instanceId"] for block in sorted(blocks, key=lambda item: item["order"])],
        "goal_ids": [node["id"] for node in nodes if node["is_goal"]],
        "layout": {"direction": "LR"},
    }
    validate_map(graph, blocks)
    return graph

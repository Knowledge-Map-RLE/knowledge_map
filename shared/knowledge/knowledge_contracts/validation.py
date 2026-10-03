"""Framework-independent validation of each persisted extraction stage.

Variant A envelope:
  - stage "linguistic": ``linguistic_profile`` (tokens, sentences, dependencies,
    phrases, sections);
  - stage "structural": structural rows (54 block types) materialized from DSL
    lines ``B T<code> B<tag> | ... | unit=S<n>``;
  - stage "map": deterministic knowledge graph whose route edges follow the
    structural type, field-reference, exact-match, and source-order contract.
"""
from __future__ import annotations
import hashlib
import re
from typing import Any, Dict, Iterable, List

from .block_types import ALL_TYPES_SET, BlockType
from .block_dsl import (DIRECT_ASSERTION_TYPES, MAP_NODE_TYPES, referenced_tags, required_fields,
                        subject_operation_issues)

class ValidationError(ValueError):
    pass

def require(condition, message):
    if not condition:
        raise ValidationError(message)

_UNIT_RE = re.compile(r"^S([1-9][0-9]*)$")
def indexed(items: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    result = {item["id"]: item for item in items}
    require(len(result) == len(items), "Duplicate identifiers")
    return result

def validate_linguistic(profile: Dict[str, Any], source: Dict[str, Any]) -> None:
    """Validate the linguistic reference layer (tokens/sentences/deps/phrases/sections)."""
    text = source["text"]
    require(hashlib.sha256(text.encode("utf-8")).hexdigest() == source["sha256"], "Source checksum mismatch")
    require(profile.get("source_revision_id") == source["id"], "Wrong linguistic source revision")
    tokens, sentences = indexed(profile["tokens"]), indexed(profile["sentences"])
    covered = bytearray(len(text))
    for token in tokens.values():
        start, end = token["start"], token["end"]
        require(0 <= start < end <= len(text), "Invalid token span")
        require(text[start:end] == token["text"], "Token does not match source")
        require(token["sentence_id"] in sentences, "Missing token sentence")
        sentence = sentences[token["sentence_id"]]
        require(sentence["start"] <= start < end <= sentence["end"], "Token outside sentence")
        require(not any(covered[start:end]), "Overlapping token spans")
        covered[start:end] = b"\x01" * (end - start)
    require(all(covered[i] or c.isspace() for i, c in enumerate(text)), "Uncovered source tokens")
    for dep in profile["dependencies"]:
        require(dep["source"] in tokens and dep["target"] in tokens, "Broken dependency")
    for phrase in profile.get("phrases", []):
        require(bool(phrase["token_ids"]) and set(phrase["token_ids"]) <= tokens.keys(), "Broken phrase")
    sections = profile.get("sections", [])
    require(sections and sections[0]["start"] == 0, "Sections do not start at document beginning")
    previous_end = 0
    for section in sections:
        require(isinstance(section["start"], int) and isinstance(section["end"], int)
                and previous_end <= section["start"] < section["end"] <= len(text),
                "Invalid/misordered section")
        require(bool(section.get("title", "").strip()), "Empty section title")
        previous_end = section["end"]
    require(previous_end == len(text), "Sections do not cover the document")

def validate_structural(blocks: List[Dict[str, Any]], source: Dict[str, Any],
                        sentences: List[Dict[str, Any]]) -> None:
    """Validate materialized structural rows against the linguistic sentences."""
    text = source["text"]
    require(sum(block.get("blockType") == "metadata" for block in blocks) <= 1,
            "Article may contain only one T1 metadata row")
    entities = indexed([{"id": b["instanceId"], **b} for b in blocks])
    tag_to_block = {b.get("data", {}).get("tag"): b for b in blocks
                    if b.get("data", {}).get("tag")}
    require(len(tag_to_block) == sum(bool(b.get("data", {}).get("tag")) for b in blocks),
            "Duplicate structural row tags")
    for block in blocks:
        require(block["schemaVersion"] == 2, "Unsupported schema")
        block_type = block["blockType"]
        require(isinstance(block_type, str) and block_type in ALL_TYPES_SET,
                "Invalid structural block type")
        require("tag" in block["data"] or block_type == "metadata", "Missing row tag")
        data = block["data"]
        require(isinstance(data, dict), "Empty typed structural block")
        missing = [field for field in required_fields(block_type) if not data.get(field)]
        require(not missing, f"Block {block_type} lacks required fields: {', '.join(missing)}")
        if block_type == "statement":
            # Whether a source-relative assertion should have been split into
            # another row is a semantic review signal, not a schema defect.
            # Keep the explicit subop/subref contract and enum checks blocking.
            operation_issues = [
                issue for issue in subject_operation_issues(data)
                if "hides a relative assertion" not in issue
            ]
            require(not operation_issues,
                    f"Block {block_type} has invalid subject operation: {'; '.join(operation_issues)}")
            subject_ref = data.get("subjectStatementRef")
            if subject_ref:
                target = entities.get(subject_ref)
                require(target is not None and target["blockType"] in DIRECT_ASSERTION_TYPES,
                        "subref= must resolve to one direct assertion block UUID")
                require(subject_ref != block["instanceId"], "subref= cannot cite itself")
        unit = data.get("unit")
        require(isinstance(unit, str) and _UNIT_RE.match(unit), "Missing or invalid unit=S<n>")
        index = int(unit[1:]) - 1
        require(0 <= index < len(sentences), f"Unit {unit} exceeds supplied sentences")
        sentence = sentences[index]
        provenance = data.get("provenance")
        require(isinstance(provenance, dict), "Missing structural provenance")
        unit_ids = provenance.get("unit_ids", [])
        spans = provenance.get("source_spans", [])
        if block_type == "metadata":
            valid_unit_ids = (isinstance(unit_ids, list) and bool(unit_ids)
                              and all(isinstance(item, str) and _UNIT_RE.fullmatch(item)
                                      for item in unit_ids))
            require(valid_unit_ids and unit_ids[0] == unit
                    and len(unit_ids) == len(set(unit_ids))
                    and unit_ids == sorted(unit_ids, key=lambda item: int(item[1:])),
                    "Metadata provenance units are missing, duplicated, or unordered")
            require(isinstance(spans, list) and len(spans) == len(unit_ids),
                    "Metadata provenance spans incomplete")
            for source_unit, span in zip(unit_ids, spans):
                source_index = int(source_unit[1:]) - 1
                require(0 <= source_index < len(sentences),
                        f"Metadata provenance unit {source_unit} exceeds supplied sentences")
                source_sentence = sentences[source_index]
                require(isinstance(span, dict), "Metadata source span must be a mapping")
                require(span.get("revision_id") == source["id"],
                        "Metadata row has wrong source revision")
                require(isinstance(span.get("start"), int) and isinstance(span.get("end"), int)
                        and span["start"] >= source_sentence["start"]
                        and span["end"] <= source_sentence["end"]
                        and span["start"] < span["end"] <= len(text),
                        "Invalid metadata source span")
        else:
            require(unit_ids == [unit], "Structural provenance unit mismatch")
            require(spans and len(spans) == 1, "Structural provenance span incomplete")
            span = spans[0]
            require(span.get("revision_id") == source["id"], "Structural row has wrong source revision")
            require(isinstance(span.get("start"), int) and isinstance(span.get("end"), int)
                    and span["start"] >= sentence["start"] and span["end"] <= sentence["end"]
                    and span["start"] < span["end"] <= len(text), "Invalid structural source span")
    for block in blocks:
        data = block["data"]
        tag = data.get("tag")
        for reference_tag in referenced_tags(block["blockType"], data):
            target = tag_to_block.get(reference_tag)
            require(target is not None,
                    f"Row {tag} references undeclared structural row {reference_tag}")
            require(reference_tag != tag,
                    f"Row {tag} cannot reference itself")
    # Nested statement references must be expandable; a two-row cycle is as
    # invalid as an immediate self-reference.
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit_subject_ref(block_id: str) -> None:
        require(block_id not in visiting, "Cycle in subject statement references")
        if block_id in visited:
            return
        visiting.add(block_id)
        reference = entities[block_id]["data"].get("subjectStatementRef")
        if reference:
            visit_subject_ref(reference)
        visiting.remove(block_id)
        visited.add(block_id)

    for block_id in entities:
        visit_subject_ref(block_id)

def validate_map(graph: Dict[str, Any], blocks: List[Dict[str, Any]]) -> None:
    """Validate the current map schema or preserve validation of persisted v1 maps."""
    schema_version = graph.get("schema_version")
    if schema_version in (None, 1):
        _validate_legacy_map(graph, blocks)
        return
    if schema_version == 3:
        _validate_v3_map(graph, blocks)
        return
    require(schema_version == 2, f"Unsupported knowledge-map schema version {schema_version!r}")

    entities = {b["instanceId"] for b in blocks}
    node_rows = graph.get("nodes", [])
    evidence_rows = graph.get("evidence", [])
    require(isinstance(node_rows, list) and isinstance(evidence_rows, list),
            "Map nodes and evidence must be lists")
    nodes = indexed(node_rows)
    evidence = indexed(evidence_rows)
    require(len(nodes) == len(node_rows) and len(evidence) == len(evidence_rows),
            "Map node and evidence ids must be unique")
    require(set(nodes).isdisjoint(evidence), "Map row cannot be both node and evidence")
    require(set(nodes) | set(evidence) == entities, "Map must account for every structural row once")

    block_by_id = {block["instanceId"]: block for block in blocks}
    require(len(block_by_id) == len(blocks), "Structural row ids must be unique")
    expected_nodes = {block["instanceId"] for block in blocks
                      if block["blockType"] in MAP_NODE_TYPES}
    require(expected_nodes <= set(nodes), "Map omits a default knowledge-map node")
    for node in nodes.values():
        identifier = node["id"]
        block = block_by_id[identifier]
        require(bool(node.get("display_text", "").strip()), "Missing display text")
        require(node.get("structural_id") == identifier, "Missing structural provenance")
        require(node.get("block_type") == block["blockType"], "Map node type differs from its row")
        require(node.get("tag") == block["data"].get("tag"), "Map node tag differs from its row")
        require(node.get("order") == block["order"], "Map node reading order differs from its row")
        require(isinstance(node.get("properties"), dict), "Map node properties must be an object")
        expected_goal = block["blockType"] in (BlockType.GOAL, BlockType.IMPACT_GOAL)
        require(node.get("is_goal") is expected_goal, "Map node goal role differs from its row")
        require(isinstance(node.get("rank"), int) and node["rank"] >= 0,
                "Map node lacks a valid left-to-right rank")

    for item in evidence.values():
        block = block_by_id[item["id"]]
        require(item.get("block_type") == block["blockType"],
                "Map evidence type differs from its row")
        require(item.get("tag") == block["data"].get("tag"), "Map evidence tag differs from its row")
        require(item.get("order") == block["order"],
                "Map evidence reading order differs from its row")
        owner_id = item.get("owner_id")
        require(owner_id is None or owner_id in nodes,
                "Map evidence owner must reference a map node")
        resolution = item.get("owner_resolution")
        require(resolution in ("unique", "ambiguous", "unattached"),
                "Map evidence has an invalid owner resolution")
        require((owner_id is not None) is (resolution == "unique"),
                "Map evidence owner resolution is inconsistent")
    for node in nodes.values():
        require(all(identifier in evidence and evidence[identifier].get("owner_id") == node["id"]
                    for identifier in node.get("evidence_refs", [])),
                "Map node has an invalid evidence reference")
    for item in evidence.values():
        owner_id = item.get("owner_id")
        require(owner_id is None or item["id"] in nodes[owner_id].get("evidence_refs", []),
                "Map evidence owner is missing its reciprocal node reference")

    reading_order = graph.get("reading_order")
    expected_order = [block["instanceId"] for block in sorted(blocks, key=lambda item: item["order"])]
    require(reading_order == expected_order,
            "Reading order must contain all structural rows in source order")
    layout = graph.get("layout")
    require(isinstance(layout, dict) and layout.get("direction") == "LR",
            "Knowledge map layout must proceed left to right")
    expected_goals = [node["id"] for node in nodes.values() if node.get("is_goal") is True]
    require(graph.get("goal_ids") == expected_goals,
            "Map goal index differs from its goal nodes")

    groups = indexed(graph.get("requirement_groups", []))
    requirement_group_rows = graph.get("requirement_groups", [])
    require(isinstance(requirement_group_rows, list)
            and len(groups) == len(requirement_group_rows),
            "Requirement group ids must be unique")
    for group in groups.values():
        require(group.get("target") in nodes, "Requirement group has a missing target node")
        require(group.get("mode") in ("all", "any"), "Invalid requirement group mode")

    adjacency = {uid: [] for uid in nodes}
    group_members: Dict[str, List[str]] = {identifier: [] for identifier in groups}
    edge_keys = set()
    edge_rows = graph.get("edges", [])
    require(isinstance(edge_rows, list), "Knowledge-map edges must be a list")
    for edge in edge_rows:
        source, target = edge.get("source"), edge.get("target")
        group_id = edge.get("group_id")
        require(source in nodes and target in nodes, "Broken knowledge-map edge")
        require(source != target, "Knowledge-map self-loop")
        require(group_id in groups and groups[group_id]["target"] == target,
                "Knowledge-map edge has an invalid requirement group")
        evidence_items = edge.get("evidence")
        require(isinstance(evidence_items, list) and bool(evidence_items),
                "Knowledge-map edge lacks provenance")
        for item in evidence_items:
            require(isinstance(item, dict) and item.get("structural_id") in entities
                    and isinstance(item.get("field"), str) and bool(item["field"]),
                    "Knowledge-map edge has invalid provenance")
        edge_key = (source, target, group_id)
        require(edge_key not in edge_keys, "Duplicate knowledge-map edge")
        edge_keys.add(edge_key)
        group_members[group_id].append(source)
        adjacency[source].append(target)
        require(nodes[source]["rank"] < nodes[target]["rank"],
                "Knowledge-map edge must point left to right")

    for group_id, group in groups.items():
        members = group_members[group_id]
        require(bool(members), "Requirement group has no edges")
        require(len(members) == len(set(members)), "Requirement group has duplicate alternatives")

    incident_node_ids = {identifier for edge in edge_rows
                         for identifier in (edge["source"], edge["target"])}
    require((set(nodes) - expected_nodes) <= incident_node_ids,
            "A non-default map node must participate in an explicit dependency")

    indegree = {identifier: 0 for identifier in nodes}
    expected_ranks = {identifier: 0 for identifier in nodes}
    for children in adjacency.values():
        for child in children:
            indegree[child] += 1
    ready = [identifier for identifier, degree in indegree.items() if degree == 0]
    visited_count = 0
    while ready:
        current = ready.pop()
        visited_count += 1
        for child in adjacency[current]:
            expected_ranks[child] = max(expected_ranks[child], expected_ranks[current] + 1)
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
    require(visited_count == len(nodes), "Knowledge-map necessary-step graph contains a cycle")
    require(all(nodes[identifier]["rank"] == rank for identifier, rank in expected_ranks.items()),
            "Map node ranks must be stable longest-path ranks")


def _validate_v3_map(graph: Dict[str, Any], blocks: List[Dict[str, Any]]) -> None:
    """Validate untyped deterministic progression edges in map schema v3."""
    entities = {block["instanceId"] for block in blocks}
    block_by_id = {block["instanceId"]: block for block in blocks}
    require(len(block_by_id) == len(blocks), "Structural row ids must be unique")
    node_rows = graph.get("nodes", [])
    evidence_rows = graph.get("evidence", [])
    require(isinstance(node_rows, list) and isinstance(evidence_rows, list),
            "Map nodes and evidence must be lists")
    nodes, evidence = indexed(node_rows), indexed(evidence_rows)
    require(set(nodes).isdisjoint(evidence), "Map row cannot be both node and evidence")
    require(set(nodes) | set(evidence) == entities,
            "Map must account for every structural row once")
    expected_nodes = {block["instanceId"] for block in blocks
                      if block["blockType"] in MAP_NODE_TYPES}
    require(set(nodes) == expected_nodes, "Map node roles differ from deterministic type registry")

    for identifier, node in nodes.items():
        block = block_by_id[identifier]
        require(bool(node.get("display_text", "").strip()), "Missing display text")
        require(node.get("structural_id") == identifier, "Missing structural provenance")
        require(node.get("block_type") == block["blockType"], "Map node type differs from its row")
        require(node.get("tag") == block["data"].get("tag"), "Map node tag differs from its row")
        require(node.get("order") == block["order"], "Map node reading order differs from its row")
        require(isinstance(node.get("properties"), dict), "Map node properties must be an object")
        expected_goal = block["blockType"] in (BlockType.GOAL, BlockType.IMPACT_GOAL)
        require(node.get("is_goal") is expected_goal, "Map node goal role differs from its row")
        require(isinstance(node.get("rank"), int) and node["rank"] >= 0,
                "Map node lacks a valid left-to-right rank")

    for identifier, item in evidence.items():
        block = block_by_id[identifier]
        require(item.get("block_type") == block["blockType"],
                "Map evidence type differs from its row")
        require(item.get("tag") == block["data"].get("tag"), "Map evidence tag differs from its row")
        require(item.get("order") == block["order"], "Map evidence order differs from its row")
        owner_id = item.get("owner_id")
        require(owner_id is None or owner_id in nodes, "Map evidence owner must reference a map node")
        resolution = item.get("owner_resolution")
        require(resolution in ("unique", "ambiguous", "unattached"),
                "Map evidence has an invalid owner resolution")
        require((owner_id is not None) is (resolution == "unique"),
                "Map evidence owner resolution is inconsistent")
    for node in nodes.values():
        require(all(identifier in evidence and evidence[identifier].get("owner_id") == node["id"]
                    for identifier in node.get("evidence_refs", [])),
                "Map node has an invalid evidence reference")
    for item in evidence.values():
        owner_id = item.get("owner_id")
        require(owner_id is None or item["id"] in nodes[owner_id].get("evidence_refs", []),
                "Map evidence owner is missing its reciprocal node reference")

    expected_order = [block["instanceId"] for block in sorted(blocks, key=lambda item: item["order"])]
    require(graph.get("reading_order") == expected_order,
            "Reading order must contain all structural rows in source order")
    require(isinstance(graph.get("layout"), dict)
            and graph["layout"].get("direction") == "LR",
            "Knowledge map layout must proceed left to right")
    expected_goals = [node["id"] for node in node_rows if node.get("is_goal") is True]
    require(graph.get("goal_ids") == expected_goals, "Map goal index differs from its goal nodes")
    require("requirement_groups" not in graph,
            "Map schema v3 must not contain requirement groups")

    adjacency = {identifier: [] for identifier in nodes}
    edge_rows = graph.get("edges", [])
    require(isinstance(edge_rows, list), "Knowledge-map edges must be a list")
    edge_keys = set()
    for edge in edge_rows:
        require(isinstance(edge, dict) and set(edge) == {"source", "target", "evidence"},
                "Map v3 edges contain only source, target, and provenance")
        source, target = edge["source"], edge["target"]
        require(source in nodes and target in nodes, "Broken knowledge-map edge")
        require(source != target, "Knowledge-map self-loop")
        key = (source, target)
        require(key not in edge_keys, "Duplicate knowledge-map edge")
        edge_keys.add(key)
        evidence_items = edge["evidence"]
        require(isinstance(evidence_items, list) and bool(evidence_items),
                "Knowledge-map edge lacks provenance")
        for witness in evidence_items:
            require(isinstance(witness, dict)
                    and set(witness) == {"structural_id", "field"}
                    and witness["structural_id"] in entities
                    and isinstance(witness["field"], str) and bool(witness["field"]),
                    "Knowledge-map edge has invalid provenance")
        adjacency[source].append(target)
        require(nodes[source]["rank"] < nodes[target]["rank"],
                "Knowledge-map edge must point left to right")

    indegree = {identifier: 0 for identifier in nodes}
    expected_ranks = {identifier: 0 for identifier in nodes}
    for children in adjacency.values():
        for child in children:
            indegree[child] += 1
    ready = [identifier for identifier, degree in indegree.items() if degree == 0]
    visited_count = 0
    while ready:
        current = ready.pop()
        visited_count += 1
        for child in adjacency[current]:
            expected_ranks[child] = max(expected_ranks[child], expected_ranks[current] + 1)
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
    require(visited_count == len(nodes), "Knowledge-map progression graph contains a cycle")
    require(all(nodes[identifier]["rank"] == rank for identifier, rank in expected_ranks.items()),
            "Map node ranks must be stable longest-path ranks")


def _validate_legacy_map(graph: Dict[str, Any], blocks: List[Dict[str, Any]]) -> None:
    """Read-only validation for historical map payloads saved before schema v2."""
    entities = {b["instanceId"] for b in blocks}
    nodes = indexed(graph.get("nodes", []))
    require(set(nodes) == entities, "Map loses structural rows")
    for node in nodes.values():
        require(bool(node.get("display_text", "").strip()), "Missing display text")
        require(node["structural_id"] in entities, "Missing structural provenance")
        require(node["block_type"] in ALL_TYPES_SET, "Invalid map node type")
    for edge in graph.get("semantic_edges", []):
        require(edge["source"] in nodes and edge["target"] in nodes, "Broken semantic reference")
        require(edge["source"] != edge["target"], "Self-loop semantic edge")
        require(bool(edge.get("relation", "").strip()), "Semantic edge lacks relation")
    adjacency = {uid: [] for uid in nodes}
    for edge in graph.get("dependency_edges", []):
        require(edge["source"] in nodes and edge["target"] in nodes, "Broken visual dependency")
        require(bool(edge.get("evidence")), "Visual dependency lacks evidence")
        adjacency[edge["source"]].append(edge["target"])
    visited, active = set(), set()
    def visit(uid):
        require(uid not in active, "Visual dependency cycle")
        if uid in visited:
            return
        active.add(uid)
        for child in adjacency[uid]:
            visit(child)
        active.remove(uid)
        visited.add(uid)
    for uid in nodes:
        visit(uid)

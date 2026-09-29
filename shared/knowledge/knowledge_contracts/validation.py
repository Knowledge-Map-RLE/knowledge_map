"""Framework-independent validation of each persisted extraction stage.

Variant A envelope:
  - stage "linguistic": ``linguistic_profile`` (tokens, sentences, dependencies,
    phrases, sections);
  - stage "structural": structural rows (54 block types) materialized from DSL
    lines ``B T<code> B<tag> | ... | unit=S<n>``;
  - stage "map": knowledge graph whose nodes are exactly the structural rows and
    whose semantic edges come only from ``relation``/``temporal_relation`` rows.
"""
from __future__ import annotations
import hashlib
import re
from typing import Any, Dict, Iterable, List

from .block_types import ALL_TYPES_SET
from .block_dsl import (DIRECT_ASSERTION_TYPES, required_fields,
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
    """Validate the knowledge map built purely from structural rows."""
    entities = {b["instanceId"] for b in blocks}
    nodes = indexed(graph["nodes"])
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

"""Контракт самостоятельных знаний: словарь участников отделён от DAG входов."""
from __future__ import annotations

import copy
import heapq
import math
import re
import unicodedata
from collections import Counter

from domain.article_maps import parse_json_response, require

SCHEMA_VERSION = 5
KNOWLEDGE_KINDS = {
    "definition", "assertion", "observation", "rule", "method", "operation",
    "result", "comparison", "conclusion", "state", "action", "goal",
}
INPUT_USAGES = {"definition", "premise", "evidence", "method", "data", "condition", "result"}
SEMANTIC_FIELDS = {
    "predicate", "roles", "inputs", "quantifier", "modality", "negated",
    "conditions", "temporal_context", "qualifiers",
}
NODE_FIELDS = {"id", "kind", "display_text", "aliases", "semantic", "provenance"}
CONCEPT_FIELDS = {"id", "display_text", "aliases", "provenance"}
INPUT_FIELDS = {"node_id", "usage", "reason", "unit_ids"}


def _fields(value, expected, name):
    require(isinstance(value, dict) and set(value) == expected, f"Invalid {name} fields")


def _text(value, name):
    require(isinstance(value, str) and bool(value.strip()), f"Empty or invalid {name}")
    require(re.search(r"[А-Яа-яЁё]", value) is None, f"{name} must be in English")


def _identity(text):
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def _unit_ids(value, units, name):
    require(isinstance(value, list) and bool(value), f"{name} requires source units")
    require(all(isinstance(i, str) and i in units for i in value), f"Unknown {name} source unit")
    require(len(value) == len(set(value)), f"Duplicate {name} source unit")


def _record(record, fields, units, identities, name):
    _fields(record, fields, name)
    _text(record["id"], f"{name} id")
    _text(record["display_text"], f"{name} display_text")
    identity = _identity(record["display_text"])
    require(identity not in identities, f"Duplicate canonical {name} text")
    identities.add(identity)
    aliases = record["aliases"]
    require(isinstance(aliases, list), f"Invalid {name} aliases")
    for alias in aliases:
        _text(alias, f"{name} alias")
    require(len(aliases) == len(set(aliases)), f"Duplicate {name} alias")
    _fields(record["provenance"], {"unit_ids"}, f"{name} provenance")
    _unit_ids(record["provenance"]["unit_ids"], units, name)
    record["provenance"]["source_spans"] = [
        {"start": units[i]["start"], "end": units[i]["end"], "section_id": units[i]["section_id"]}
        for i in record["provenance"]["unit_ids"]
    ]


def validate_knowledge_map(value: object, source: dict) -> dict:
    """Проверяет знания и обоснованные входы; роли никогда не создают стрелок."""
    _fields(value, {"schema_version", "concepts", "nodes", "edges"}, "knowledge graph")
    require(type(value["schema_version"]) is int and value["schema_version"] == SCHEMA_VERSION,
            "Expected knowledge-map schema version 5")
    require(isinstance(value["concepts"], list), "Concept dictionary must be a list")
    require(isinstance(value["nodes"], list) and bool(value["nodes"]), "Map must contain knowledge blocks")
    require(isinstance(value["edges"], list), "Map edges must be a list")
    graph = copy.deepcopy(value)
    units = {unit["id"]: unit for unit in source["units"]}
    concepts, nodes, ids = {}, {}, set()
    concept_texts, node_texts = set(), set()
    for concept in graph["concepts"]:
        _record(concept, CONCEPT_FIELDS, units, concept_texts, "concept")
        require(concept["id"] not in ids, "Duplicate concept id")
        ids.add(concept["id"])
        concepts[concept["id"]] = concept
    for order, node in enumerate(graph["nodes"]):
        _record(node, NODE_FIELDS, units, node_texts, "knowledge block")
        require(node["id"] not in ids, "Duplicate or overlapping knowledge-block id")
        ids.add(node["id"])
        require(isinstance(node["kind"], str) and node["kind"] in KNOWLEDGE_KINDS,
                "Unknown knowledge kind; bare concept names belong in the dictionary")
        semantic = node["semantic"]
        _fields(semantic, SEMANTIC_FIELDS, "knowledge semantic")
        _text(semantic["predicate"], "knowledge predicate")
        for field in ("quantifier", "modality", "temporal_context"):
            if semantic[field] is not None:
                _text(semantic[field], field)
        require(type(semantic["negated"]) is bool, "Invalid negation")
        require(isinstance(semantic["conditions"], list), "Invalid conditions")
        for condition in semantic["conditions"]:
            _text(condition, "condition")
        _fields(semantic["qualifiers"], {"attributes"}, "knowledge qualifiers")
        attributes = semantic["qualifiers"]["attributes"]
        require(isinstance(attributes, list), "Invalid qualifier attributes")
        attribute_names = set()
        for attribute in attributes:
            _fields(attribute, {"name", "value", "unit"}, "qualifier attribute")
            _text(attribute["name"], "qualifier name")
            identity = _identity(attribute["name"])
            require(identity not in attribute_names, "Duplicate qualifier name")
            attribute_names.add(identity)
            value = attribute["value"]
            require(value is None or type(value) in (str, int, float, bool), "Invalid qualifier value")
            if isinstance(value, str):
                _text(value, "qualifier value")
            if type(value) is float:
                require(math.isfinite(value), "Nonfinite qualifier value")
            if attribute["unit"] is not None:
                _text(attribute["unit"], "qualifier unit")
        require(isinstance(semantic["roles"], list), "Invalid participant roles")
        require(isinstance(semantic["inputs"], list), "Invalid knowledge inputs")
        node.update(order=order, rank=0, origin="extracted", block_type=node["kind"],
                    is_goal=node["kind"] == "goal")
        nodes[node["id"]] = node

    used_concepts, declared_pairs = set(), set()
    for node in graph["nodes"]:
        roles = set()
        for role in node["semantic"]["roles"]:
            _fields(role, {"role", "concept_id", "node_id"}, "participant role")
            _text(role["role"], "participant role")
            concept_id, node_id = role["concept_id"], role["node_id"]
            require((concept_id is None) != (node_id is None), "Participant must reference exactly one concept or block")
            if concept_id is not None:
                require(isinstance(concept_id, str) and concept_id in concepts, "Unknown semantic concept")
                used_concepts.add(concept_id)
            else:
                require(isinstance(node_id, str) and node_id in nodes, "Unknown semantic knowledge block")
                require(node_id != node["id"], "Self-reference in participant roles")
            key = (role["role"], concept_id, node_id)
            require(key not in roles, "Duplicate participant role")
            roles.add(key)
        inputs = set()
        for knowledge_input in node["semantic"]["inputs"]:
            _fields(knowledge_input, INPUT_FIELDS, "knowledge input")
            parent = knowledge_input["node_id"]
            require(isinstance(parent, str) and parent in nodes, "Unknown knowledge input")
            require(parent != node["id"], "Knowledge-map self-loop")
            require(parent not in inputs, "Duplicate knowledge input")
            inputs.add(parent)
            require(isinstance(knowledge_input["usage"], str) and knowledge_input["usage"] in INPUT_USAGES,
                    "Unknown knowledge-input usage")
            _text(knowledge_input["reason"], "dependency reason")
            _unit_ids(knowledge_input["unit_ids"], units, "dependency")
            anchors = set(node["provenance"]["unit_ids"]) | set(nodes[parent]["provenance"]["unit_ids"])
            require(bool(set(knowledge_input["unit_ids"]) & anchors),
                    "Dependency evidence must include endpoint provenance")
            declared_pairs.add((parent, node["id"]))
    # Неиспользуемое название словаря не является утверждением или ребром DAG.
    # Его происхождение уже проверено; диагностируем избыток без потери корректных знаний.
    unused_concepts = sorted(set(concepts) - used_concepts)

    pairs = set()
    outgoing = {i: [] for i in nodes}
    indegree = {i: 0 for i in nodes}
    for edge in graph["edges"]:
        _fields(edge, {"source", "target"}, "edge")
        require(isinstance(edge["source"], str) and isinstance(edge["target"], str), "Invalid edge ids")
        pair = (edge["source"], edge["target"])
        require(all(i in nodes for i in pair), "Unknown edge endpoint; dictionary entries are not DAG nodes")
        require(pair[0] != pair[1], "Knowledge-map self-loop")
        require(pair not in pairs, "Duplicate edge")
        pairs.add(pair)
        outgoing[pair[0]].append(pair[1])
        indegree[pair[1]] += 1
    require(pairs == declared_pairs, "Every edge must match exactly one justified knowledge input")
    ready = [(nodes[i]["order"], i) for i, degree in indegree.items() if degree == 0]
    heapq.heapify(ready)
    visited = 0
    while ready:
        _, identifier = heapq.heappop(ready)
        visited += 1
        for child in outgoing[identifier]:
            nodes[child]["rank"] = max(nodes[child]["rank"], nodes[identifier]["rank"] + 1)
            indegree[child] -= 1
            if indegree[child] == 0:
                heapq.heappush(ready, (nodes[child]["order"], child))
    require(visited == len(nodes), "Knowledge-map dependencies contain a cycle")
    graph["reading_order"] = [n["id"] for n in sorted(graph["nodes"], key=lambda n: (n["rank"], n["order"]))]
    graph["analysis"] = {
        "depth": max(n["rank"] for n in graph["nodes"]) + 1,
        "layer_counts": {str(rank): count for rank, count in sorted(Counter(n["rank"] for n in graph["nodes"]).items())},
        "knowledge_input_count": len(pairs), "concept_count": len(concepts),
        "operation_count": sum(n["kind"] == "operation" for n in graph["nodes"]),
    }
    if unused_concepts:
        graph["analysis"]["unused_concept_ids"] = unused_concepts
    return graph


def parse_knowledge_map(raw: str, source: dict) -> dict:
    return validate_knowledge_map(parse_json_response(raw), source)


def model_contract(graph: dict) -> dict:
    """Убирает только серверные поля для повторной независимой проверки результата."""
    return {"schema_version": graph["schema_version"],
            "concepts": [{key: copy.deepcopy(c[key]) for key in CONCEPT_FIELDS - {"provenance"}}
                         | {"provenance": {"unit_ids": list(c["provenance"]["unit_ids"])}}
                         for c in graph["concepts"]],
            "nodes": [{key: copy.deepcopy(n[key]) for key in NODE_FIELDS - {"provenance"}}
                      | {"provenance": {"unit_ids": list(n["provenance"]["unit_ids"])}}
                      for n in graph["nodes"]], "edges": copy.deepcopy(graph["edges"])}


def knowledge_text_keys(nodes: list[dict]) -> dict[str, str]:
    """Привязывает короткие ключи к полным текстам внутри конкретной ревизии карты."""
    ordered = sorted(nodes, key=lambda node: (node["display_text"], node["id"]))
    return {node["id"]: f"T{index + 1}" for index, node in enumerate(ordered)}


def dependency_review_view(graph: dict) -> dict:
    """Прикрепляет рабочий ключ непосредственно к тексту без изменения знаний."""
    view = model_contract(graph)
    keys = knowledge_text_keys(view["nodes"])
    concepts = {concept["id"]: "C:" + concept["id"] for concept in view["concepts"]}
    for concept in view["concepts"]:
        concept["id"] = concepts[concept["id"]]
    for node in view["nodes"]:
        node["id"] = keys[node["id"]]
        for role in node["semantic"]["roles"]:
            if role["concept_id"] is not None:
                role["concept_id"] = concepts[role["concept_id"]]
            if role["node_id"] is not None:
                role["node_id"] = keys[role["node_id"]]
        for knowledge_input in node["semantic"]["inputs"]:
            knowledge_input["node_id"] = keys[knowledge_input["node_id"]]
    for edge in view["edges"]:
        edge.update(source=keys[edge["source"]], target=keys[edge["target"]])
    return view


def apply_dependency_review(raw: str, graph: dict, source: dict, *,
                            target_keys: list[str] | None = None) -> dict:
    """Проверяет полный набор или новую группу входов вместе с существующим DAG."""
    review = parse_json_response(raw)
    _fields(review, {"dependencies"}, "dependency review")
    require(isinstance(review["dependencies"], list), "Dependencies must be a directed-edge array")
    candidate = model_contract(graph)
    nodes = {n["id"]: n for n in candidate["nodes"]}
    text_keys = knowledge_text_keys(candidate["nodes"])
    by_text_key = {key: identifier for identifier, key in text_keys.items()}
    if target_keys is None:
        for node in nodes.values():
            node["semantic"]["inputs"] = []
        candidate["edges"] = []
        pairs = set()
    else:
        require(isinstance(target_keys, list) and bool(target_keys), "Empty dependency target scope")
        require(all(isinstance(key, str) and key in by_text_key for key in target_keys),
                "Unknown dependency target scope")
        require(len(target_keys) == len(set(target_keys)), "Duplicate dependency target scope")
        require(all(not nodes[by_text_key[key]]["semantic"]["inputs"] for key in target_keys),
                "Dependency batch cannot replace accepted target inputs")
        pairs = {(text_keys[edge["source"]], text_keys[edge["target"]]) for edge in candidate["edges"]}
    for dependency in review["dependencies"]:
        _fields(dependency, {"source", "target", "usage", "reason", "unit_ids"}, "review dependency")
        parent_key, target_key = dependency["source"], dependency["target"]
        require(isinstance(parent_key, str) and parent_key in by_text_key, "Unknown review source text key")
        require(isinstance(target_key, str) and target_key in by_text_key, "Unknown review target text key")
        require(target_keys is None or target_key in target_keys, "Dependency target is outside its batch")
        pair = (parent_key, target_key)
        require(pair not in pairs, "Duplicate knowledge input")
        pairs.add(pair)
        parent, target = by_text_key[parent_key], by_text_key[target_key]
        nodes[target]["semantic"]["inputs"].append({
            "node_id": parent,
            **{key: dependency[key] for key in ("usage", "reason", "unit_ids")},
        })
        candidate["edges"].append({"source": parent, "target": target})
    return validate_knowledge_map(candidate, source)

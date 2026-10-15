"""Модель 6: канонические знания, вхождения и DAG непосредственных переходов."""
from __future__ import annotations

import copy
import heapq
import math
import re
import unicodedata
from collections import Counter, defaultdict, deque

from domain.article_maps import parse_json_response, require

SCHEMA_VERSION = 6
KINDS = {"state", "action"}
KNOWLEDGE_KINDS = {"definition", "assertion", "observation", "rule", "method", "operation",
                   "result", "comparison", "conclusion", "state", "action", "goal", "limitation"}
ACTION_STATUSES = {"performed", "planned", "prescribed", "unresolved"}
USAGES = {"definition", "premise", "evidence", "method", "data", "condition", "result",
          "development", "prerequisite"}
LOGICS = {"single", "conjunction", "contrast", "argument", "partition"}
CONCEPT_FIELDS = {"id", "display_text", "aliases", "provenance"}
KNOWLEDGE_FIELDS = {"knowledge_id", "kind", "knowledge_kind", "display_text", "aliases",
                    "action_status", "semantic_frame", "grounding", "provenance"}
STATEMENT_FIELDS = {"statement_id", "predicate", "roles", "quantifier", "modality", "negated",
                    "conditions", "temporal_context", "qualifiers", "provenance"}
OCCURRENCE_FIELDS = {"id", "knowledge_id", "occurrence_context", "duplication"}
TRANSITION_FIELDS = {"id", "sources", "target", "usage", "reason", "unit_ids", "conditions"}
GRAPH_FIELDS = {"schema_version", "concepts", "knowledge", "nodes", "edges", "transitions"}


def fields(value, expected, name):
    require(isinstance(value, dict) and set(value) == expected, f"Invalid {name} fields")


def text(value, name):
    require(isinstance(value, str) and bool(value.strip()), f"Empty or invalid {name}")
    require(re.search(r"[А-Яа-яЁё]", value) is None, f"{name} must be in English")


def identity(value):
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def member(value, allowed):
    return isinstance(value, str) and value in allowed


def strings(value, name):
    require(isinstance(value, list), f"Invalid {name}")
    for item in value:
        text(item, name)
    require(len(value) == len(set(value)), f"Duplicate {name}")


def units(value, source_units, name):
    strings(value, name)
    require(bool(value) and all(item in source_units for item in value), f"Unknown or empty {name} source units")


def provenance(value, source_units, name):
    fields(value, {"unit_ids"}, name)
    units(value["unit_ids"], source_units, name)
    value["source_spans"] = [{"start": source_units[u]["start"], "end": source_units[u]["end"],
                              "section_id": source_units[u]["section_id"]} for u in value["unit_ids"]]


def _topology(nodes, pairs):
    outgoing = {n: [] for n in nodes}
    incoming = {n: [] for n in nodes}
    for parent, child in pairs:
        require(parent in nodes and child in nodes, "Unknown visible edge endpoint")
        require(parent != child, "Visible DAG self-loop")
        outgoing[parent].append(child)
        incoming[child].append(parent)
    indegree = {n: len(incoming[n]) for n in nodes}
    rank = dict.fromkeys(nodes, 0)
    order = {n: index for index, n in enumerate(nodes)}
    ready = [(order[n], n) for n, degree in indegree.items() if degree == 0]
    heapq.heapify(ready)
    visited = []
    while ready:
        _, parent = heapq.heappop(ready)
        visited.append(parent)
        for child in outgoing[parent]:
            rank[child] = max(rank[child], rank[parent] + 1)
            indegree[child] -= 1
            if indegree[child] == 0:
                heapq.heappush(ready, (order[child], child))
    require(len(visited) == len(nodes), "Visible knowledge-development DAG contains a cycle")
    return outgoing, incoming, rank


def _check_occurrences(nodes, pairs, source_units):
    outgoing, incoming, _ = _topology(nodes, pairs)
    by_knowledge = defaultdict(list)
    for node in nodes.values():
        by_knowledge[node["knowledge_id"]].append(node)
    for occurrences in by_knowledge.values():
        require(occurrences[0]["duplication"] is None, "Primary occurrence cannot declare duplication")
        for other in occurrences[1:]:
            justification = other["duplication"]
            require(justification is not None, "Repeated occurrence requires semantic justification")
            require(other["occurrence_context"] is not None, "Repeated occurrence requires chain context")
            for previous in occurrences[:occurrences.index(other)]:
                require(previous["occurrence_context"] != other["occurrence_context"],
                        "Mergeable occurrences have the same chain context")
                a, b = previous["id"], other["id"]
                merged_nodes = {i: n for i, n in nodes.items() if i != b}
                merged_pairs = {(a if p == b else p, a if c == b else c) for p, c in pairs}
                cycle = False
                try:
                    _topology(merged_nodes, merged_pairs)
                except ValueError:
                    cycle = True
                # Разные входы И выходы задают риск ложного скрещивания цепочек.
                distinct_paths = (bool(incoming[a]) and bool(incoming[b]) and bool(outgoing[a])
                                  and bool(outgoing[b]) and set(incoming[a]) != set(incoming[b])
                                  and set(outgoing[a]) != set(outgoing[b]))
                require(cycle or distinct_paths, "Repeated occurrence can be merged without changing chains")
            endpoint_units = set(nodes[other["id"]]["provenance"]["unit_ids"])
            require(bool(endpoint_units.intersection(justification["unit_ids"])),
                    "Duplication justification must anchor its knowledge")
    # Произведение двух конечных DAG обнаруживает одинаковые полные цепочки,
    # не перечисляя экспоненциальное множество всех путей.
    roots = [i for i in nodes if not incoming[i]]
    pending = deque((a, b, a != b) for a in roots for b in roots
                    if nodes[a]["knowledge_id"] == nodes[b]["knowledge_id"])
    seen = set()
    while pending:
        a, b, different = pending.popleft()
        if (a, b, different) in seen:
            continue
        seen.add((a, b, different))
        require(not (different and not outgoing[a] and not outgoing[b]), "Duplicate canonical knowledge chain")
        for child_a in outgoing[a]:
            for child_b in outgoing[b]:
                if nodes[child_a]["knowledge_id"] == nodes[child_b]["knowledge_id"]:
                    pending.append((child_a, child_b, different or child_a != child_b))


def validate_development_map(value, source, *, extraction=False, final=True):
    """Проверяет семантику без ограничения её циклов; ранги выводит только из DAG."""
    fields(value, GRAPH_FIELDS, "development graph")
    require(type(value["schema_version"]) is int and value["schema_version"] == SCHEMA_VERSION,
            "Expected knowledge-map schema version 6")
    graph = copy.deepcopy(value)
    for name in ("concepts", "knowledge", "nodes", "edges", "transitions"):
        require(isinstance(graph[name], list), f"Invalid development {name}")
    require(bool(graph["knowledge"]), "Map must contain canonical knowledge")
    source_units = {u["id"]: u for u in source["units"]}
    concepts, knowledge, nodes, ids = {}, {}, {}, set()
    concept_texts, knowledge_meanings = set(), set()
    for concept in graph["concepts"]:
        fields(concept, CONCEPT_FIELDS, "concept")
        text(concept["id"], "concept id")
        require(concept["id"] not in ids, "Duplicate concept id")
        ids.add(concept["id"])
        text(concept["display_text"], "concept display text")
        name = identity(concept["display_text"])
        require(name not in concept_texts, "Duplicate canonical concept")
        concept_texts.add(name)
        strings(concept["aliases"], "concept aliases")
        provenance(concept["provenance"], source_units, "concept provenance")
        concepts[concept["id"]] = concept
    statement_ids = set()
    for item in graph["knowledge"]:
        fields(item, KNOWLEDGE_FIELDS, "canonical knowledge")
        kid = item["knowledge_id"]
        text(kid, "knowledge id")
        require(kid not in ids, "Duplicate canonical knowledge id")
        ids.add(kid)
        require(member(item["kind"], KINDS) and member(item["knowledge_kind"], KNOWLEDGE_KINDS), "Invalid knowledge kind")
        require(member(item["grounding"], {"source_explicit", "source_argument"}), "Invalid knowledge grounding")
        require((item["kind"] == "state" and item["action_status"] is None)
                or (item["kind"] == "action" and member(item["action_status"], ACTION_STATUSES)), "Invalid action status")
        text(item["display_text"], "knowledge display text")
        strings(item["aliases"], "knowledge aliases")
        provenance(item["provenance"], source_units, "knowledge provenance")
        frame = item["semantic_frame"]
        fields(frame, {"logic", "statements"}, "semantic frame")
        require(member(frame["logic"], LOGICS) and isinstance(frame["statements"], list) and bool(frame["statements"]),
                "Invalid semantic frame")
        require(frame["logic"] != "single" or len(frame["statements"]) == 1, "Single frame must contain one statement")
        for statement in frame["statements"]:
            fields(statement, STATEMENT_FIELDS, "semantic statement")
            text(statement["statement_id"], "statement id")
            require(statement["statement_id"] not in statement_ids, "Duplicate semantic statement id")
            statement_ids.add(statement["statement_id"])
            text(statement["predicate"], "predicate")
            require(type(statement["negated"]) is bool, "Invalid statement negation")
            for field in ("quantifier", "modality", "temporal_context"):
                if statement[field] is not None:
                    text(statement[field], field)
            strings(statement["conditions"], "statement conditions")
            require(isinstance(statement["roles"], list), "Invalid statement roles")
            provenance(statement["provenance"], source_units, "statement provenance")
            require(set(statement["provenance"]["unit_ids"]).issubset(item["provenance"]["unit_ids"]),
                    "Statement provenance must be included in knowledge provenance")
            qualifiers = statement["qualifiers"]
            fields(qualifiers, {"attributes"}, "statement qualifiers")
            require(isinstance(qualifiers["attributes"], list), "Invalid qualifier attributes")
            names = set()
            for attribute in qualifiers["attributes"]:
                fields(attribute, {"name", "value", "unit"}, "qualifier")
                text(attribute["name"], "qualifier name")
                key = identity(attribute["name"])
                require(key not in names, "Duplicate qualifier name")
                names.add(key)
                require(attribute["value"] is None or type(attribute["value"]) in {str, int, float, bool},
                        "Invalid qualifier value")
                if isinstance(attribute["value"], str):
                    text(attribute["value"], "qualifier value")
                if type(attribute["value"]) is float:
                    require(math.isfinite(attribute["value"]), "Nonfinite qualifier")
                if attribute["unit"] is not None:
                    text(attribute["unit"], "qualifier unit")
        knowledge[kid] = item
    used_concepts = set()
    for item in graph["knowledge"]:
        semantic_identity = []
        for statement in item["semantic_frame"]["statements"]:
            role_keys = set()
            for role in statement["roles"]:
                fields(role, {"role", "concept_id", "knowledge_id"}, "semantic role")
                text(role["role"], "role")
                cid, kid = role["concept_id"], role["knowledge_id"]
                require((cid is None) != (kid is None), "Role must reference exactly one semantic participant")
                require((isinstance(cid, str) and cid in concepts) or (isinstance(kid, str) and kid in knowledge),
                        "Unknown semantic participant")
                if cid is not None:
                    used_concepts.add(cid)
                key = (role["role"], cid, kid)
                require(key not in role_keys, "Duplicate participant role")
                role_keys.add(key)
            semantic_identity.append({k: v for k, v in statement.items() if k not in {"statement_id", "provenance"}})
        from domain.article_maps import fingerprint
        semantic_identity = copy.deepcopy(semantic_identity)
        for meaning in semantic_identity:
            meaning["predicate"] = identity(meaning["predicate"])
            meaning["roles"] = sorted(meaning["roles"], key=fingerprint)
            meaning["conditions"] = sorted(meaning["conditions"], key=identity)
            meaning["qualifiers"]["attributes"] = sorted(meaning["qualifiers"]["attributes"], key=lambda a: identity(a["name"]))
        if item["semantic_frame"]["logic"] != "argument":
            semantic_identity.sort(key=fingerprint)
        signature = fingerprint({"kind": item["kind"], "action_status": item["action_status"],
                                 "logic": item["semantic_frame"]["logic"], "statements": semantic_identity})
        require(signature not in knowledge_meanings, "Duplicate canonical knowledge meaning")
        knowledge_meanings.add(signature)
    require(used_concepts == set(concepts), "Unused canonical concept")
    if extraction:
        require(not graph["nodes"] and not graph["edges"] and not graph["transitions"],
                "Extraction must leave occurrences and transitions to dependency review")
        return graph
    require(bool(graph["nodes"]), "Map requires visible occurrences")
    for index, node in enumerate(graph["nodes"]):
        fields(node, OCCURRENCE_FIELDS, "visible occurrence")
        text(node["id"], "occurrence id")
        require(node["id"] not in ids, "Duplicate or overlapping occurrence id")
        ids.add(node["id"])
        require(isinstance(node["knowledge_id"], str) and node["knowledge_id"] in knowledge, "Unknown occurrence knowledge")
        if node["occurrence_context"] is not None:
            text(node["occurrence_context"], "occurrence context")
        if node["duplication"] is not None:
            fields(node["duplication"], {"reason", "unit_ids"}, "occurrence duplication")
            text(node["duplication"]["reason"], "duplication reason")
            units(node["duplication"]["unit_ids"], source_units, "duplication")
        item = knowledge[node["knowledge_id"]]
        node.update(display_text=item["display_text"], kind=item["kind"], block_type=item["kind"],
                    knowledge_kind=item["knowledge_kind"], is_goal=item["knowledge_kind"] == "goal",
                    order=index, rank=0, origin="extracted", provenance=copy.deepcopy(item["provenance"]))
        nodes[node["id"]] = node
    require({n["knowledge_id"] for n in nodes.values()} == set(knowledge), "Knowledge lacks a visible occurrence")
    declared_pairs, transition_ids, transition_signatures = set(), set(), set()
    for transition in graph["transitions"]:
        fields(transition, TRANSITION_FIELDS, "transition")
        text(transition["id"], "transition id")
        require(transition["id"] not in transition_ids, "Duplicate transition id")
        transition_ids.add(transition["id"])
        strings(transition["sources"], "transition sources")
        require(bool(transition["sources"]), "Transition requires immediate inputs")
        require(isinstance(transition["target"], str) and transition["target"] in nodes and all(s in nodes for s in transition["sources"]),
                "Unknown transition occurrence")
        require(transition["target"] not in transition["sources"], "Visible transition self-loop")
        require(member(transition["usage"], USAGES), "Invalid transition usage")
        text(transition["reason"], "transition reason")
        units(transition["unit_ids"], source_units, "transition")
        strings(transition["conditions"], "transition conditions")
        anchors = set(nodes[transition["target"]]["provenance"]["unit_ids"])
        for parent in transition["sources"]:
            anchors.update(nodes[parent]["provenance"]["unit_ids"])
            declared_pairs.add((parent, transition["target"]))
        require(bool(anchors.intersection(transition["unit_ids"])), "Transition must anchor endpoint provenance")
        from domain.article_maps import fingerprint
        signature = fingerprint({"sources": sorted(transition["sources"]), "target": transition["target"],
                                 "conditions": sorted(transition["conditions"])})
        require(signature not in transition_signatures, "Duplicate transition premise group")
        transition_signatures.add(signature)
    pairs = set()
    for edge in graph["edges"]:
        fields(edge, {"source", "target"}, "visible edge")
        require(isinstance(edge["source"], str) and isinstance(edge["target"], str), "Invalid edge reference")
        pair = edge["source"], edge["target"]
        require(pair not in pairs, "Duplicate visible edge")
        pairs.add(pair)
    require(pairs == declared_pairs, "Visible edges must exactly project justified transitions")
    outgoing, incoming, rank = _topology(nodes, pairs)
    if final:
        _check_occurrences(nodes, pairs, source_units)
    for identifier, node in nodes.items():
        node["rank"] = rank[identifier]
    counts = Counter(rank.values())
    graph["reading_order"] = sorted(nodes, key=lambda n: (rank[n], nodes[n]["order"]))
    graph["analysis"] = {"depth": max(rank.values(), default=-1) + 1,
                         "layer_counts": {str(k): v for k, v in sorted(counts.items())},
                         "concept_count": len(concepts), "canonical_knowledge_count": len(knowledge),
                         "occurrence_count": len(nodes), "repeated_occurrence_count": len(nodes) - len(knowledge),
                         "transition_count": len(graph["transitions"]), "knowledge_input_count": len(pairs),
                         "statement_count": len(statement_ids),
                         "operation_count": sum(k["kind"] == "action" for k in knowledge.values()),
                         "isolated_count": sum(not outgoing[n] and not incoming[n] for n in nodes)}
    return graph


def model_contract(graph):
    """Убирает только производные серверные поля, сохраняя машинную семантику."""
    # Порядок ключей стабилен между процессами: точный запрос входит в хеш этапа.
    value = {k: copy.deepcopy(graph[k]) for k in ("schema_version", "concepts", "knowledge", "nodes", "edges", "transitions")}
    for concept in value["concepts"]:
        concept["provenance"] = {"unit_ids": concept["provenance"]["unit_ids"]}
    for item in value["knowledge"]:
        item["provenance"] = {"unit_ids": item["provenance"]["unit_ids"]}
        for statement in item["semantic_frame"]["statements"]:
            statement["provenance"] = {"unit_ids": statement["provenance"]["unit_ids"]}
    value["nodes"] = [{k: n[k] for k in ("id", "knowledge_id", "occurrence_context", "duplication")} for n in value["nodes"]]
    return value


def initialize_occurrences(graph, source):
    value = model_contract(graph)
    value["nodes"] = [{"id": f"B{i + 1}", "knowledge_id": k["knowledge_id"],
                       "occurrence_context": None, "duplication": None} for i, k in enumerate(value["knowledge"])]
    return validate_development_map(value, source)


def apply_development_review(raw, graph, source, *, target_keys=None, final=False):
    response = parse_json_response(raw)
    fields(response, {"occurrences", "transitions"}, "development review")
    require(isinstance(response["occurrences"], list) and isinstance(response["transitions"], list),
            "Invalid development review arrays")
    value = model_contract(graph)
    value["nodes"].extend(copy.deepcopy(response["occurrences"]))
    by_id = {n["id"]: n for n in value["nodes"]}
    for transition in response["transitions"]:
        fields(transition, TRANSITION_FIELDS, "transition")
        require(isinstance(transition["target"], str) and transition["target"] in by_id, "Unknown transition target")
        require(target_keys is None or by_id[transition["target"]]["knowledge_id"] in target_keys,
                "Transition target is outside its canonical knowledge group")
    value["transitions"].extend(copy.deepcopy(response["transitions"]))
    pairs = {(s, t["target"]) for t in value["transitions"] for s in t["sources"]}
    value["edges"] = [{"source": a, "target": b} for a, b in sorted(pairs)]
    return validate_development_map(value, source, final=final)

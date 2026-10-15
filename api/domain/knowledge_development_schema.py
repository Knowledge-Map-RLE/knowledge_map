"""Закрытые схемы извлечения знаний и обзора переходов модели 6."""
from domain.knowledge_development import ACTION_STATUSES, KINDS, KNOWLEDGE_KINDS, LOGICS, USAGES


def obj(properties):
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def text():
    return {"type": "string", "minLength": 1}


def texts(*, nonempty=False):
    return {"type": "array", "items": text(), **({"minItems": 1} if nonempty else {})}


def provenance():
    return obj({"unit_ids": texts(nonempty=True)})


def occurrence_schema(knowledge_ids=None):
    reference = {"type": "string", "enum": knowledge_ids} if knowledge_ids else text()
    return obj({"id": text(), "knowledge_id": reference,
                "occurrence_context": {"type": ["string", "null"]},
                "duplication": {"anyOf": [{"type": "null"}, obj({"reason": text(), "unit_ids": texts(nonempty=True)})]}})


def transition_schema():
    return obj({"id": text(), "sources": texts(nonempty=True), "target": text(),
                "usage": {"type": "string", "enum": sorted(USAGES)}, "reason": text(),
                "unit_ids": texts(nonempty=True), "conditions": texts()})


def development_map_json_schema(*, extraction=False):
    nullable = {"type": ["string", "null"]}
    statement = obj({"statement_id": text(), "predicate": text(), "roles": {"type": "array", "items": {"anyOf": [
        obj({"role": text(), "concept_id": text(), "knowledge_id": {"type": "null"}}),
        obj({"role": text(), "concept_id": {"type": "null"}, "knowledge_id": text()}),
    ]}}, "quantifier": nullable, "modality": nullable, "negated": {"type": "boolean"},
        "conditions": texts(), "temporal_context": nullable,
        "qualifiers": obj({"attributes": {"type": "array", "items": obj({
            "name": text(), "value": {"type": ["string", "number", "boolean", "null"]}, "unit": nullable})}}),
        "provenance": provenance()})
    schema = obj({"schema_version": {"type": "integer", "const": 6},
        "concepts": {"type": "array", "items": obj({"id": text(), "display_text": text(),
                                                    "aliases": texts(), "provenance": provenance()})},
        "knowledge": {"type": "array", "minItems": 1, "items": obj({
            "knowledge_id": text(), "kind": {"type": "string", "enum": sorted(KINDS)},
            "knowledge_kind": {"type": "string", "enum": sorted(KNOWLEDGE_KINDS)},
            "display_text": text(), "aliases": texts(),
            "action_status": {"type": ["string", "null"], "enum": [None, *sorted(ACTION_STATUSES)]},
            "grounding": {"type": "string", "enum": ["source_explicit", "source_argument"]},
            "semantic_frame": obj({"logic": {"type": "string", "enum": sorted(LOGICS)},
                                   "statements": {"type": "array", "minItems": 1, "items": statement}}),
            "provenance": provenance()})},
        "nodes": {"type": "array", "items": occurrence_schema()},
        "edges": {"type": "array", "items": obj({"source": text(), "target": text()})},
        "transitions": {"type": "array", "items": transition_schema()}})
    if extraction:
        for field in ("nodes", "edges", "transitions"):
            schema["properties"][field]["maxItems"] = 0
    return schema


def development_review_json_schema(knowledge_ids):
    return obj({"occurrences": {"type": "array", "items": occurrence_schema(knowledge_ids)},
                "transitions": {"type": "array", "items": transition_schema()}})

"""JSON Schema входного ответа LLM для независимого контракта карты."""
from domain.article_maps import NODE_KINDS, REIFIED_KINDS, SEMANTIC_FIELDS


def reified_map_json_schema() -> dict:
    """Описывает обязательные поля; содержательные инварианты проверяет домен."""
    def obj(properties):
        return {"type": "object", "properties": properties,
                "required": list(properties), "additionalProperties": False}

    text = {"type": "string", "minLength": 1}
    optional_text = {"type": ["string", "null"]}
    strings = {"type": "array", "items": text}
    role_list = {"type": "array", "items": obj({"role": text, "node_id": text})}
    semantic_fields = {
        "predicate": optional_text,
        "roles": role_list,
        "quantifier": optional_text, "modality": optional_text,
        "negated": {"type": "boolean"}, "conditions": strings,
        "temporal_context": optional_text,
        # Научные ограничения имеют открытые имена и JSON-значения.
        "qualifiers": {"type": "object", "additionalProperties": True},
    }
    assert set(semantic_fields) == SEMANTIC_FIELDS

    def node(kinds, *, reified=False):
        semantic = obj({**semantic_fields,
                        "predicate": text if reified else optional_text,
                        "roles": {**role_list, "minItems": 1} if reified else role_list})
        return obj({"id": text, "kind": {"type": "string", "enum": sorted(kinds)},
                    "display_text": text, "aliases": strings, "semantic": semantic,
                    "provenance": obj({"unit_ids": {**strings, "minItems": 1}})})

    return obj({
        "schema_version": {"type": "integer", "const": 4},
        # Две непересекающиеся ветви отражают тот же инвариант, что и валидатор.
        "nodes": {"type": "array", "minItems": 1, "items": {"anyOf": [
            node(NODE_KINDS - REIFIED_KINDS), node(REIFIED_KINDS, reified=True)]}},
        "edges": {"type": "array", "items": obj({"source": text, "target": text})},
    })

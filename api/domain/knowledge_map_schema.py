"""JSON Schema знаний и отдельного полного аудита их зависимостей."""
from domain.knowledge_map import INPUT_USAGES, KNOWLEDGE_KINDS, SCHEMA_VERSION


def _object(properties):
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def _text():
    return {"type": "string", "minLength": 1}


def _units():
    return {"type": "array", "minItems": 1, "items": _text()}


def _input_properties():
    return {"usage": {"type": "string", "enum": sorted(INPUT_USAGES)}, "reason": _text(), "unit_ids": _units()}


def knowledge_map_json_schema() -> dict:
    optional_text = {"type": ["string", "null"]}
    strings = {"type": "array", "items": _text()}
    record = {"id": _text(), "display_text": _text(), "aliases": strings,
              "provenance": _object({"unit_ids": _units()})}
    semantic = _object({
        "predicate": _text(),
        "roles": {"type": "array", "items": {"anyOf": [
            _object({"role": _text(), "concept_id": _text(), "node_id": {"type": "null"}}),
            _object({"role": _text(), "concept_id": {"type": "null"}, "node_id": _text()}),
        ]}},
        "inputs": {"type": "array", "items": _object({"node_id": _text(), **_input_properties()})},
        "quantifier": optional_text, "modality": optional_text, "negated": {"type": "boolean"},
        "conditions": strings, "temporal_context": optional_text,
        "qualifiers": _object({"attributes": {"type": "array", "items": _object({
            "name": _text(), "value": {"type": ["string", "number", "boolean", "null"]},
            "unit": optional_text})}}),
    })
    return _object({
        "schema_version": {"type": "integer", "const": SCHEMA_VERSION},
        "concepts": {"type": "array", "items": _object(record)},
        "nodes": {"type": "array", "minItems": 1, "items": _object({
            **record, "kind": {"type": "string", "enum": sorted(KNOWLEDGE_KINDS)}, "semantic": semantic})},
        "edges": {"type": "array", "items": _object({"source": _text(), "target": _text()})},
    })


def dependency_review_json_schema(nodes: list[dict], target_keys: list[str] | None = None,
                                 accepted_dependencies: list[dict] | None = None) -> dict:
    """Закрытая strict-схема фиксирует оба конца каждой направленной связи."""
    from domain.knowledge_map import knowledge_text_keys
    text_keys = knowledge_text_keys(nodes)
    # Общий enum и общий payload не дублируют грамматику для каждого блока.
    source_reference = {"type": "string", "enum": list(text_keys.values())}
    if target_keys is not None:
        from domain.article_maps import require
        require(isinstance(target_keys, list) and bool(target_keys)
                and all(isinstance(key, str) and key in text_keys.values() for key in target_keys)
                and len(target_keys) == len(set(target_keys)), "Invalid dependency schema target scope")
        # Выбираем цель и разрешаем только остальные известные источники.
        # Конечная regex-альтернатива не размножает enum за лимит провайдера.
        # При этом не используются неподдерживаемые not/if/allOf или lookaround.
        accepted = accepted_dependencies if accepted_dependencies is not None else []
        require(isinstance(accepted, list), "Invalid accepted dependency schema prefix")
        outgoing = {key: [] for key in text_keys.values()}
        for edge in accepted:
            require(isinstance(edge, dict) and isinstance(edge.get("source"), str)
                    and isinstance(edge.get("target"), str)
                    and edge["source"] in outgoing and edge["target"] in outgoing
                    and edge["source"] != edge["target"], "Invalid accepted dependency schema edge")
            outgoing[edge["source"]].append(edge["target"])
        branches = []
        for target in target_keys:
            # Уже известный путь target -> source запрещает добавлять обратный вход.
            forbidden, pending = {target}, [target]
            while pending:
                for child in outgoing[pending.pop()]:
                    if child not in forbidden:
                        forbidden.add(child)
                        pending.append(child)
            allowed = [key for key in text_keys.values() if key not in forbidden]
            if allowed:
                branches.append(_object({
                    "target": {"type": "string", "const": target},
                    "source": {"type": "string", "pattern": "^(?:" + "|".join(allowed) + ")$"},
                    "usage": {"$ref": "#/$defs/usage"},
                    "reason": _text(), "unit_ids": _units(),
                }))
        if not branches:
            return _object({"dependencies": {"type": "array", "maxItems": 0, "items": _text()}})
        schema = _object({"dependencies": {"type": "array", "items": {"$ref": "#/$defs/input"}}})
        schema["$defs"] = {"input": {"anyOf": branches},
                           "usage": {"type": "string", "enum": sorted(INPUT_USAGES)}}
        return schema
    knowledge_input = _object({
        "source": {"$ref": "#/$defs/source_reference"},
        "target": {"$ref": "#/$defs/source_reference"},
        "usage": {"type": "string", "enum": sorted(INPUT_USAGES)},
        "reason": _text(), "unit_ids": _units(),
    })
    schema = _object({"dependencies": {"type": "array", "items": {"$ref": "#/$defs/input"}}})
    schema["$defs"] = {"source_reference": source_reference, "input": knowledge_input}
    return schema


def extraction_map_json_schema() -> dict:
    """Первый этап извлекает знания; все зависимости строит отдельный этап."""
    schema = knowledge_map_json_schema()
    schema["properties"]["edges"]["maxItems"] = 0
    semantic = schema["properties"]["nodes"]["items"]["properties"]["semantic"]
    semantic["properties"]["inputs"]["maxItems"] = 0
    return schema

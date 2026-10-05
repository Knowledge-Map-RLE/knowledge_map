"""Независимый контракт реифицированной карты и проверка её инвариантов."""
from __future__ import annotations

import copy
import hashlib
import heapq
import json
import re
import unicodedata
from datetime import datetime, timezone
from uuid import uuid4

PIPELINES = ("text_reified", "structural_rows")
NODE_KINDS = {
    "concept", "object", "class", "property", "state", "action", "process",
    "comparison", "rule", "assertion", "goal", "topic",
}
REIFIED_KINDS = {"assertion", "rule", "comparison"}
SEMANTIC_FIELDS = {
    "predicate", "roles", "quantifier", "modality", "negated",
    "conditions", "temporal_context", "qualifiers",
}


class ArticleMapError(ValueError):
    """Ошибка контракта карты или её входных данных."""


class ArticleMapNotFound(ArticleMapError):
    """Статья или сохранённая карта отсутствует."""


class ArticleMapAccessDenied(ArticleMapError):
    """Пользователь не является владельцем статьи."""


class ArticleMapBusy(ArticleMapError):
    """Для этого пайплайна статьи уже выполняется преобразование."""


class ArticleMapConflict(ArticleMapError):
    """Вход или сохранённый результат изменился во время операции."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ArticleMapError(message)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def fingerprint(value: object) -> str:
    return digest(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def prepare_source(article_id: str, text: str) -> dict:
    """Размечает исходный Markdown без NLP и без изменения координат текста."""
    require(isinstance(text, str) and bool(text.strip()), "Full article text is required")
    references = re.search(
        r"(?im)^\s*(?:#{1,6}\s+)?(?:references|reference list|bibliography|works cited|"
        r"literature cited|references and notes)(?:\s*[\[(].*?[\])])?\s*:?\s*$",
        text,
    )
    content_end = references.start() if references else len(text)
    content = text[:content_end]
    sections = []
    for match in re.finditer(r"(?m)^#{1,6}\s+([^\r\n]+)", content):
        sections.append({"id": f"H{len(sections) + 1}", "title": match.group(1), "start": match.start()})
    if not sections or sections[0]["start"] > 0:
        sections.insert(0, {"id": "H0", "title": "Preamble", "start": 0})
    for index, section in enumerate(sections):
        section["end"] = sections[index + 1]["start"] if index + 1 < len(sections) else content_end
    units = []
    # Заголовки остаются контекстом; параграфы и таблицы сохраняют точные диапазоны.
    for match in re.finditer(r"[^\r\n]+(?:\r?\n(?!\s*\r?$)[^\r\n]+)*", content, re.MULTILINE):
        section = next((item for item in reversed(sections) if item["start"] <= match.start()), sections[0])
        units.append({"id": f"U{len(units) + 1}", "start": match.start(), "end": match.end(),
                      "section_id": section["id"], "text": match.group()})
    require(bool(units), "Article contains no source units")
    return {"article_id": article_id, "text": text, "sha256": digest(text),
            "offset_encoding": "unicode_codepoints", "content_end": content_end,
            "references_excluded": references is not None, "sections": sections, "units": units}


def _fields(value: object, expected: set[str], name: str) -> None:
    require(isinstance(value, dict) and set(value) == expected, f"Invalid {name} fields")


def _text(value: object, name: str, *, english: bool = False) -> None:
    require(isinstance(value, str) and bool(value.strip()), f"Empty or invalid {name}")
    if english:
        require(re.search(r"[А-Яа-яЁё]", value) is None, f"{name} must be in English")


def _identity(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def validate_reified_map(value: object, source: dict) -> dict:
    """Проверяет ответ модели и вычисляет устойчивую топологическую раскладку."""
    _fields(value, {"schema_version", "nodes", "edges"}, "graph")
    require(type(value["schema_version"]) is int and value["schema_version"] == 4, "Expected knowledge-map schema version 4")
    require(isinstance(value["nodes"], list) and bool(value["nodes"]), "Map must contain nodes")
    require(isinstance(value["edges"], list), "Map edges must be a list")
    graph = copy.deepcopy(value)
    units = {unit["id"]: unit for unit in source["units"]}
    by_id = {}
    identities = set()
    for order, node in enumerate(graph["nodes"]):
        _fields(node, {"id", "kind", "display_text", "aliases", "semantic", "provenance"}, "node")
        _text(node["id"], "node id")
        require(node["id"] not in by_id, "Duplicate node id")
        require(isinstance(node["kind"], str) and node["kind"] in NODE_KINDS, "Unknown node kind")
        _text(node["display_text"], "display_text", english=True)
        identity = _identity(node["display_text"])
        require(identity not in identities, "Duplicate canonical node text")
        identities.add(identity)
        require(isinstance(node["aliases"], list) and all(isinstance(a, str) and a.strip() for a in node["aliases"]),
                "Invalid aliases")
        require(len(node["aliases"]) == len(set(node["aliases"])), "Duplicate aliases")
        _fields(node["provenance"], {"unit_ids"}, "provenance")
        unit_ids = node["provenance"]["unit_ids"]
        require(isinstance(unit_ids, list) and bool(unit_ids) and all(isinstance(i, str) and i in units for i in unit_ids),
                "Node must reference existing source units")
        require(len(unit_ids) == len(set(unit_ids)), "Duplicate source-unit references")
        semantic = node["semantic"]
        _fields(semantic, SEMANTIC_FIELDS, "semantic")
        for field in ("predicate", "quantifier", "modality", "temporal_context"):
            require(semantic[field] is None or isinstance(semantic[field], str), f"Invalid semantic {field}")
            if semantic[field] is not None:
                _text(semantic[field], field, english=True)
        require(type(semantic["negated"]) is bool, "Invalid negation")
        require(isinstance(semantic["conditions"], list) and all(isinstance(c, str) and c.strip() for c in semantic["conditions"]),
                "Invalid conditions")
        require(isinstance(semantic["qualifiers"], dict), "Invalid qualifiers")
        require(isinstance(semantic["roles"], list), "Invalid semantic roles")
        role_keys = set()
        for role in semantic["roles"]:
            _fields(role, {"role", "node_id"}, "role")
            _text(role["role"], "role", english=True)
            _text(role["node_id"], "role node_id")
            key = (role["role"], role["node_id"])
            require(key not in role_keys, "Duplicate semantic role")
            role_keys.add(key)
        if node["kind"] in REIFIED_KINDS:
            require(bool(semantic["predicate"]) and bool(semantic["roles"]),
                    "Reified statements require a predicate and participant roles")
        node.update(order=order, rank=0, origin="extracted", block_type=node["kind"],
                    is_goal=node["kind"] == "goal")
        node["provenance"]["source_spans"] = [
            {"start": units[i]["start"], "end": units[i]["end"], "section_id": units[i]["section_id"]}
            for i in unit_ids
        ]
        by_id[node["id"]] = node
    pairs = set()
    outgoing = {identifier: [] for identifier in by_id}
    indegree = {identifier: 0 for identifier in by_id}
    for edge in graph["edges"]:
        _fields(edge, {"source", "target"}, "edge")
        require(isinstance(edge["source"], str) and isinstance(edge["target"], str), "Invalid edge ids")
        pair = (edge["source"], edge["target"])
        require(all(identifier in by_id for identifier in pair), "Unknown edge endpoint")
        require(pair[0] != pair[1], "Knowledge-map self-loop")
        require(pair not in pairs, "Duplicate edge")
        pairs.add(pair)
        outgoing[pair[0]].append(pair[1])
        indegree[pair[1]] += 1
    for node in graph["nodes"]:
        for role in node["semantic"]["roles"]:
            require(role["node_id"] in by_id, "Unknown semantic participant")
            pair = (role["node_id"], node["id"])
            require(pair[0] != pair[1], "Knowledge-map self-loop in semantic roles")
            # Роль уже объявляет участника непосредственным смысловым входом.
            # Материализуем эту декларацию, не добавляя научного утверждения.
            if pair not in pairs:
                pairs.add(pair)
                outgoing[pair[0]].append(pair[1])
                indegree[pair[1]] += 1
                graph["edges"].append({"source": pair[0], "target": pair[1]})
    if len(graph["nodes"]) > 1:
        require(bool(pairs), "A multi-block article map cannot be an isolated concept inventory")
        require(any(n["kind"] in REIFIED_KINDS for n in graph["nodes"]),
                "An article map must include source-grounded reified statements")
    ready = [(by_id[i]["order"], i) for i, degree in indegree.items() if degree == 0]
    heapq.heapify(ready)
    visited = 0
    while ready:
        _, identifier = heapq.heappop(ready)
        visited += 1
        for child in outgoing[identifier]:
            by_id[child]["rank"] = max(by_id[child]["rank"], by_id[identifier]["rank"] + 1)
            indegree[child] -= 1
            if indegree[child] == 0:
                heapq.heappush(ready, (by_id[child]["order"], child))
    require(visited == len(by_id), "Knowledge-map dependencies contain a cycle")
    graph["reading_order"] = [node["id"] for node in sorted(graph["nodes"], key=lambda n: (n["rank"], n["order"]))]
    return graph


def parse_json_response(raw: str):
    """Принимает только полный JSON без Markdown и без неоднозначных ключей."""
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "Duplicate JSON key")
            result[key] = value
        return result
    try:
        value = json.loads(raw, object_pairs_hook=unique_object,
                           parse_constant=lambda value: require(False, f"Invalid JSON constant: {value}"))
    except (json.JSONDecodeError, TypeError) as exc:
        raise ArticleMapError("Model returned invalid or incomplete JSON") from exc
    return value


def parse_model_map(raw: str, source: dict) -> dict:
    return validate_reified_map(parse_json_response(raw), source)


def new_result(article_id: str, pipeline_id: str, graph: dict, input_fingerprint: str, **metadata) -> dict:
    require(pipeline_id in PIPELINES, "Unknown map pipeline")
    return {"article_id": article_id, "pipeline_id": pipeline_id, "run_id": str(uuid4()),
            "updated_at": timestamp(), "input_fingerprint": input_fingerprint,
            "graph": graph, "graph_schema_version": graph["schema_version"],
            "builder_version": "1" if pipeline_id == "text_reified" else str(graph["schema_version"]),
            "translations": {}, **metadata}

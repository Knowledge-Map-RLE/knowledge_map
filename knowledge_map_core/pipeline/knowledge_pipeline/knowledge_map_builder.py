"""Построение Карты Знаний из структурных строк (Вариант A).

Карта полностью производна от структурных строк: каждый блок — узел (все 54 типа
равны, спец-ролей entity/statement нет); семантические рёбра возникают из
явных ``relation``/``temporal_relation`` и типизированных ссылок операции над
утверждением. Они не превращаются в dependency-рёбра. Разрешение конечных точек:
  - приоритет — явные B-теги (``srcRef``/``tgtRef``);
  - fallback — детерминированный поиск текста endpoints по заявленным полям строк;
  - при отсутствии/неоднозначности совпадения ребро не строится (без гадания).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from knowledge_contracts.block_dsl import REF_FIELDS, REFS_FIELDS
from knowledge_contracts.block_types import BlockType
from knowledge_contracts.dsl_tags import iter_tags
from knowledge_contracts.validation import require, validate_map

_SKIP_FIELDS = {"tag", "unit", "provenance", "source", "_extra"}
_LABEL_FIELDS = (
    "subject", "object", "parameter", "term", "definition", "hypothesis", "mechanism",
    "target", "groupName", "species", "stepName", "experimentName", "claimSubject",
    "claimObject", "novelty", "resultsSummary", "agingConnection", "canonicalName",
    "findings", "postClaims", "sideFindings", "futureResearch", "openQuestions",
)


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
        if key in _SKIP_FIELDS or key in REF_FIELDS or key in REFS_FIELDS:
            continue
        if value in (None, "", [], {}):
            continue
        rendered = ", ".join(str(item) for item in value) if isinstance(value, list) else str(value)
        parts.append(f"{key}: {rendered}")
    return " | ".join(parts) if parts else block_type


def _row_labels(block: Dict[str, Any]) -> List[str]:
    labels: List[str] = []
    data = block["data"]
    for key in _LABEL_FIELDS:
        value = data.get(key)
        if isinstance(value, list):
            labels.extend(str(item) for item in value if item)
        elif value:
            labels.append(str(value))
    return labels


def _match_score(query: str, label: str) -> int:
    q = " ".join(query.lower().split())
    l = " ".join(str(label).lower().split())
    if not q or not l:
        return 0
    if l == q:
        return 100
    if q in l:
        return 50
    if l in q:
        return 30
    if len(q.split()) > 1 and all(word in l for word in q.split()):
        return 10
    return 0


def _resolve_text(query: Optional[str], candidates: Dict[str, List[str]],
                  exclude: Set[str]) -> Optional[str]:
    """Детерминированный поиск единственного победителя среди строк-кандидатов."""
    if not query:
        return None
    best_score, best_tags = 0, []
    for tag, labels in candidates.items():
        if tag in exclude:
            continue
        for label in labels:
            score = _match_score(query, label)
            if score > best_score:
                best_score, best_tags = score, [tag]
            elif score == best_score and score:
                best_tags.append(tag)
    return best_tags[0] if best_score and len(set(best_tags)) == 1 else None


def _ref_tags(value: Any) -> List[str]:
    if not value:
        return []
    return iter_tags(str(value))


def _endpoint(block: Dict[str, Any], ref_key: Optional[str], text_key: str,
              candidates: Dict[str, List[str]], tags_to_instance: Dict[str, str]) -> tuple[Optional[str], str]:
    if ref_key:
        ref_value = block["data"].get(ref_key)
        ref_tags = _ref_tags(ref_value)
        if ref_tags:
            resolved = tags_to_instance.get(ref_tags[0])
            require(resolved is not None, f"{block['data']['tag']} refs undeclared row {ref_tags[0]}")
            return resolved, "ref"
    text_value = block["data"].get(text_key)
    if not text_value:
        return None, "none"
    resolved = _resolve_text(text_value, candidates, {block["data"]["tag"]})
    return (tags_to_instance.get(resolved), "text") if resolved else (None, "none")


def build_knowledge_map(blocks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Строит граф Карты Знаний по структурным строкам и валидирует его."""
    tags_to_instance = {block["data"]["tag"]: block["instanceId"] for block in blocks}
    candidates = {block["data"]["tag"]: _row_labels(block) for block in blocks}
    nodes = [{
        "id": block["instanceId"], "block_type": block["blockType"],
        "tag": block["data"]["tag"], "order": block["order"],
        "structural_id": block["instanceId"], "display_text": _display_text(block),
    } for block in blocks]
    semantic_edges: List[Dict[str, Any]] = []
    for block in blocks:
        block_type = block["blockType"]
        if block_type == BlockType.STATEMENT and block["data"].get("subjectStatementRef"):
            semantic_edges.append({
                "source": block["data"]["subjectStatementRef"],
                "target": block["instanceId"],
                "relation": "subject_operation:" + block["data"]["subjectOperation"],
                "relation_tag": block["data"]["tag"],
                "block": block["instanceId"],
                "resolution": "ref",
            })
        elif block_type == BlockType.RELATION:
            source, source_resolution = _endpoint(
                block, "sourceRef", "source", candidates, tags_to_instance)
            target, target_resolution = _endpoint(
                block, "targetRef", "target", candidates, tags_to_instance)
            if source and target and source != target:
                semantic_edges.append({
                    "source": source, "target": target,
                    "relation": block["data"].get("relationType", ""),
                    "relation_tag": block["data"]["tag"], "block": block["instanceId"],
                    "resolution": "ref" if "ref" in (source_resolution, target_resolution) else "text",
                })
        elif block_type == BlockType.TEMPORAL_RELATION:
            source, source_resolution = _endpoint(
                block, None, "earlier", candidates, tags_to_instance)
            target, target_resolution = _endpoint(
                block, None, "later", candidates, tags_to_instance)
            if source and target and source != target:
                semantic_edges.append({
                    "source": source, "target": target,
                    "relation": block["data"].get("relationType", "precedes"),
                    "relation_tag": block["data"]["tag"], "block": block["instanceId"],
                    "resolution": "ref" if "ref" in (source_resolution, target_resolution) else "text",
                })
    graph = {"nodes": nodes, "semantic_edges": semantic_edges, "dependency_edges": []}
    validate_map(graph, blocks)
    return graph

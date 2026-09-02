"""
Выявление паттернов по структуре графа утверждений: представление подграфа.

Утверждения (KnowledgeStatement) статьи приводятся к типизированному подграфу
{nodes, edges}, который является AST-деревом утверждений статьи:

  * каждый узел — участник триплета: концепт ('concept'), литерал ('literal')
    или вложенное утверждение ('ST|<предикат>|<тип субъекта>|<тип объекта>');
  * id концепта/литерала — нормализованный текст (общий концепт, встречающийся
    в нескольких утверждениях, даёт один узел);
  * id вложенного утверждения — его uid: если subject_type/object_type ==
    'statement' и текст совпадает с uid другого утверждения этого же документа,
    узел связывается с реальным утверждением (сохраняется дерево вложенности);
  * рёбра — сами утверждения: from = узел субъекта, to = узел объекта,
    label = нормализованный предикат.

Такой граф сопоставим между статьями (стабильные метки узлов и предикатов),
поэтому подграфы разных статей можно копать частотными алгоритмами
(gSpan в services/gspan.py) и накладывать найденные паттерны на конкретный
результат поиска для генерации новых знаний.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Предикаты, не несущие доменной структуры (служебные META-утверждения).
_NOISE_PREDICATES = {"is_a", "contains", "related_to", "has"}

_DIRECTION_UP = {"increase", "increases", "increased", "up", "upregulate", "upregulates",
                 "upregulated", "raise", "raises", "promote", "promotes", "stimulate",
                 "stimulates", "activate", "activates", "повыш", "увеличив", "стимул",
                 "активир", "растет", "растёт"}
_DIRECTION_DOWN = {"decrease", "decreases", "decreased", "down", "downregulate",
                   "downregulates", "downregulated", "reduce", "reduces", "suppress",
                   "suppresses", "inhibit", "inhibits", "пониж", "сниж", "угнет",
                   "подавл", "тормоз"}
_DIRECTION_UNCHANGED = {"unchanged", "no change", "constant", "no effect", "без изменений"}


def normalize_predicate(predicate: str, mode: str = "raw") -> str:
    """Нормализация предиката утверждения.

    Args:
        predicate: исходный предикат.
        mode:
          * "raw" — как есть (нижний регистр, обрезание пробелов/знаков);
          * "direction" — свёртка в направление up|down|unchanged|other;
          * "bucket" — как "direction", но без потери текста:
            "<направление>:<текст>".
    """
    p = (predicate or "").strip().lower()
    p = re.sub(r"[\s_]+", " ", p)
    p = re.sub(r"[^a-zа-я0-9 ]", "", p)
    if not p:
        return "_"
    if mode == "raw":
        return p
    direction = "other"
    for token in _DIRECTION_UP:
        if token in p:
            direction = "up"
            break
    if direction == "other":
        for token in _DIRECTION_DOWN:
            if token in p:
                direction = "down"
                break
    if direction == "other":
        for token in _DIRECTION_UNCHANGED:
            if token in p:
                direction = "unchanged"
                break
    if mode == "direction":
        return direction
    return f"{direction}:{p}"


def entity_type(subject_type: Any = None, object_type: Any = None) -> str:
    """Метка узла по типу субъекта/объекта (concept|literal)."""
    raw = str(subject_type or object_type or "concept").strip().lower()
    if raw == "literal":
        return "literal"
    return "concept"


def statement_shape(stmt: Dict[str, Any], predicate_mode: str = "raw") -> str:
    """Каноническая «форма» утверждения как узла AST-дерева."""
    pred = normalize_predicate(str(stmt.get("predicate") or ""), predicate_mode)
    st = str(stmt.get("subject_type") or "concept").strip().lower() or "concept"
    ot = str(stmt.get("object_type") or "concept").strip().lower() or "concept"
    st = "concept" if st not in {"statement", "literal"} else st
    ot = "concept" if ot not in {"statement", "literal"} else ot
    return f"ST|{pred}|{st}|{ot}"


def _norm(text: str) -> str:
    t = (text or "").strip().lower()
    t = re.sub(r"\s+", " ", t)
    return t or "_"


def statement_shape_label(shape: str) -> str:
    """Читаемая строка AST-узла вида 'ST|увеличивает|concept|concept'."""
    return shape


def statements_to_graph(
    doc_id: str,
    statements: Sequence[Dict[str, Any]],
    predicate_mode: str = "raw",
    exclude_noise: bool = True,
    max_nodes: Optional[int] = None,
) -> Dict[str, Any]:
    """Строит AST-граф утверждений статьи.

    Args:
        doc_id: идентификатор статьи (графа корпуса).
        statements: список утверждений — словари с ключами
            uid, subject_text, predicate, object_text, subject_type, object_type.
        predicate_mode: режим нормализации предикатов (см. normalize_predicate).
        exclude_noise: отбрасывать служебные META-предикаты (is_a/contains/...).
        max_nodes: если задан, узлы графа ограничиваются этим числом (детерминированно
            по частоте связности), чтобы майнинг оставался практичным для больших статей.

    Returns:
        {"id", "nodes": [{"id", "label"}], "edges": [{"from", "to", "label"}],
         "raw": [{"subject_text", "predicate", "object_text"}],
         "node_text": {node_id: читаемый текст}, "count": int}
    """
    rows: List[Dict[str, Any]] = []
    for st in statements or []:
        subj = str(st.get("subject_text") or "").strip()
        pred = str(st.get("predicate") or "").strip()
        obj = str(st.get("object_text") or "").strip()
        if not subj or not obj or not pred:
            continue
        if exclude_noise and pred.lower() in _NOISE_PREDICATES:
            continue
        rows.append(st)

    uid_to_row: Dict[str, Dict[str, Any]] = {str(r.get("uid")): r for r in rows if r.get("uid")}

    def resolve_node(text: str, typ: Any) -> Tuple[str, str]:
        """(id, label) узла: концепт/литерал по тексту или вложенное утверждение по uid."""
        raw_typ = str(typ or "").strip().lower()
        if raw_typ == "statement":
            inner = uid_to_row.get(text)
            if inner is not None:
                return str(inner.get("uid")), statement_shape(inner, predicate_mode)
            return _norm(text), "statement"
        return _norm(text), ("literal" if raw_typ == "literal" else "concept")

    nodes: Dict[str, str] = {}
    edges: List[Dict[str, str]] = []
    raw: List[Dict[str, str]] = []
    node_text: Dict[str, str] = {}

    def record_node(nid: str, label: str, text: str, typ: Any) -> None:
        nodes.setdefault(nid, label)
        if nid in node_text:
            return
        if label.startswith("ST|"):
            inner = uid_to_row.get(nid)
            node_text[nid] = readable_statement_text(inner) if inner else str(text)
        elif label == "statement":
            node_text[nid] = str(text)
        else:
            node_text[nid] = str(text)

    for st in rows:
        subj = str(st.get("subject_text") or "").strip()
        pred = str(st.get("predicate") or "").strip()
        obj = str(st.get("object_text") or "").strip()
        subj_id, subj_label = resolve_node(subj, st.get("subject_type"))
        obj_id, obj_label = resolve_node(obj, st.get("object_type"))
        record_node(subj_id, subj_label, subj, st.get("subject_type"))
        record_node(obj_id, obj_label, obj, st.get("object_type"))
        edges.append({"from": subj_id, "to": obj_id, "label": normalize_predicate(pred, predicate_mode)})
        raw.append({"subject_text": subj, "predicate": pred, "object_text": obj,
                    "subject_type": st.get("subject_type", ""),
                    "object_type": st.get("object_type", "")})

    # Ограничение размера графа для практичного майнинга больших статей.
    if max_nodes and len(nodes) > max_nodes:
        degree: Dict[str, int] = {}
        for e in edges:
            degree[e["from"]] = degree.get(e["from"], 0) + 1
            degree[e["to"]] = degree.get(e["to"], 0) + 1
        keep = {nid for nid, _ in sorted(degree.items(), key=lambda kv: (-kv[1], kv[0]))[:max_nodes]}
        nodes = {nid: lab for nid, lab in nodes.items() if nid in keep}
        edges = [e for e in edges if e["from"] in keep and e["to"] in keep]

    # дедупликация рёбер
    seen = set()
    dedup: List[Dict[str, str]] = []
    for e in edges:
        key = (e["from"], e["to"], e["label"])
        if key in seen:
            continue
        seen.add(key)
        dedup.append(e)
    edges = dedup

    return {
        "id": doc_id,
        "nodes": [{"id": nid, "label": label} for nid, label in nodes.items()],
        "edges": edges,
        "raw": raw,
        "node_text": node_text,
        "count": len(raw),
    }


def dedupe_graph_edges(graph: Dict[str, Any]) -> Dict[str, Any]:
    """Убирает дубликаты рёбер (одинаковые from/to/label)."""
    seen = set()
    edges = []
    for e in graph.get("edges") or []:
        key = (e.get("from"), e.get("to"), e.get("label"))
        if key in seen:
            continue
        seen.add(key)
        edges.append(e)
    return {**graph, "edges": edges}


def readable_statement_text(stmt: Dict[str, Any]) -> str:
    """Читаемый текст утверждения для кандидатов и примеров."""
    return f"{stmt.get('subject_text')} {stmt.get('predicate')} {stmt.get('object_text')}"
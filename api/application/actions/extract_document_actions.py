"""
Layer: Application (Use Cases)
Package: application.actions.extract_document_actions
Responsibility: Извлечение действий и причинно-следственных цепочек из аннотаций документа.

Allowed imports: domain, application.ports, application.actions (extractors)
Forbidden imports: fastapi, neomodel, grpc, aioboto3, adapters, infrastructure, web
"""
from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from typing import List, Tuple

from domain.rules.graph_acyclicity import would_create_cycle
from domain.exceptions import NotFoundError

# Citation pattern: [1], [2,3], [1, 2, 3], [1-3] — but NOT inside metadata or References
_CITATION_RE = re.compile(r'\[\d[\d,;\s\-]*\]')

logger = logging.getLogger(__name__)


def _strip_citations(text: str) -> Tuple[str, List[Tuple[int, int]]]:
    """Remove inline citation markers like [1], [2, 3], [1-4] from text.

    Returns:
        stripped_text: text with citations replaced by empty string
        offset_map: list of (stripped_pos, original_pos) checkpoints,
                    sorted by stripped_pos. Used to remap char positions.
    """
    result = []
    offset_map: List[Tuple[int, int]] = []
    prev_end = 0
    cumulative_removed = 0
    for m in _CITATION_RE.finditer(text):
        # append text before this citation
        result.append(text[prev_end:m.start()])
        # record checkpoint: after this removal, stripped_pos maps to original pos
        stripped_pos_after = len(''.join(result))
        original_pos_after = m.end()
        removed_here = m.end() - m.start()
        cumulative_removed += removed_here
        offset_map.append((stripped_pos_after, cumulative_removed))
        prev_end = m.end()
    result.append(text[prev_end:])
    return ''.join(result), offset_map


def _remap_char_pos(stripped_pos: int, offset_map: List[Tuple[int, int]]) -> int:
    """Map a position in stripped text back to position in original text."""
    if not offset_map:
        return stripped_pos
    # Binary search: find cumulative_removed at this stripped_pos
    lo, hi = 0, len(offset_map) - 1
    cumulative = 0
    for spos, cum in offset_map:
        if stripped_pos >= spos:
            cumulative = cum
        else:
            break
    return stripped_pos + cumulative


# Вербы → action_class
_RESULT_VERBS = {
    "reduce", "restore", "increase", "decrease", "improve", "protect", "damage",
    "cause", "produce", "enhance", "inhibit", "prevent", "block", "suppress",
    "induce", "generate", "promote", "rescue", "attenuate", "ameliorate",
    "exacerbate", "accelerate", "delay", "arrest", "halt", "reverse",
}
_MECHANISM_VERBS = {
    "mediate", "activate", "phosphorylate", "bind", "regulate", "modulate",
    "catalyze", "ubiquitinate", "acetylate", "methylate", "cleave", "recruit",
    "sequester", "stabilize", "degrade", "translocate", "oligomerize",
    "aggregate", "fold", "unfold", "interact", "associate", "localize",
}


def _assign_action_class(verb_lemma: str) -> str:
    v = verb_lemma.lower()
    if v in _RESULT_VERBS:
        return "result"
    if v in _MECHANISM_VERBS:
        return "mechanism"
    return "action"


@dataclass
class ExtractActionsResult:
    actions_count: int
    edges_count: int
    pending_count: int


async def extract_document_actions(
    doc_id: str,
    document_repo,
    action_repo,
    nlp_client,
    storage,
    clear_existing: bool = False,
) -> ExtractActionsResult:
    """
    Извлекает действия из полного текста документа через NLP-сервис и строит граф LEADS_TO.
    Обрабатывает весь markdown документа одним вызовом NLP-сервиса.
    """
    # 1. Проверяем документ
    doc = document_repo.get_by_id(doc_id)
    if doc is None:
        raise NotFoundError(f"Document {doc_id} not found")

    # 2. Загружаем полный markdown текст
    key = doc.get_active_markdown_key()
    if not key:
        raise NotFoundError(f"Document {doc_id} has no markdown key")
    full_text = await storage.download_text(doc.s3_bucket, key)
    if not full_text:
        raise NotFoundError(f"Document {doc_id} markdown is empty")

    # Фильтруем frontmatter и References (так же как NLP-сервис)
    frontmatter = re.match(r'^---\r?\n.*?\r?\n---\r?\n', full_text, re.DOTALL)
    if frontmatter:
        full_text = full_text[frontmatter.end():]
    ref = re.search(r'\n##\s+References\b', full_text, re.IGNORECASE)
    if ref:
        full_text = full_text[:ref.start()]

    logger.info("[actions] doc=%s: text_len=%d", doc_id, len(full_text))

    # Strip inline citations ([1], [2,3] etc.) before NLP analysis so they don't
    # confuse the parser. Build offset_map to remap char positions back afterward.
    nlp_text, citation_offset_map = _strip_citations(full_text)
    citations_removed = len(full_text) - len(nlp_text)
    if citations_removed:
        logger.info("[actions] doc=%s: stripped %d citation chars", doc_id, citations_removed)

    # 3. Очистка при необходимости
    if clear_existing:
        action_repo.delete_for_document(doc_id)

    # 4. Один вызов NLP-сервиса на весь документ
    try:
        result = await nlp_client.extract_actions(nlp_text, doc_id=doc_id)
    except Exception as e:
        logger.error("[actions] NLP service error for doc %s: %s", doc_id, e)
        raise

    nlp_actions = result.get("actions", [])
    nlp_deps = result.get("dependencies", [])
    logger.info("[actions] doc=%s: NLP returned %d actions, %d deps", doc_id, len(nlp_actions), len(nlp_deps))

    all_action_rows: List[dict] = []
    all_action_edges: List[dict] = []

    # Build uid_map: NLP action_id → persistent uuid
    uid_map: dict[str, str] = {}
    for a in nlp_actions:
        persistent_uid = str(uuid.uuid4())
        uid_map[a["action_id"]] = persistent_uid
        action_class = _assign_action_class(a["verb_lemma"])
        # Remap char positions from stripped text back to original text positions
        char_start = _remap_char_pos(a["char_start"], citation_offset_map)
        char_end = _remap_char_pos(a["char_end"], citation_offset_map)
        all_action_rows.append({
            'uid': persistent_uid,
            'verb': a["verb_lemma"],
            'verb_text': a["verb_text"],
            'full_phrase': a["full_phrase"],
            'subject': None,
            'object': a["object_text"] or None,
            'sentence_text': a["sentence_text"],
            'char_start': char_start,
            'char_end': char_end,
            'doc_id': doc_id,
            'annotation_uid': None,
            'action_class': action_class,
        })

    # Build action→action edges, separating marker-based (LEADS_TO) from syntactic (SYNTACTIC_DEP)
    all_syntactic_edges: List[dict] = []
    for dep in nlp_deps:
        src_uid = uid_map.get(dep["source_id"])
        tgt_uid = uid_map.get(dep["target_id"])
        if not src_uid or not tgt_uid or src_uid == tgt_uid:
            continue

        evidence_type = dep.get("evidence_type", "marker")

        if evidence_type == "syntactic":
            # Syntactic deps → separate SYNTACTIC_DEP edges, no DAG check
            all_syntactic_edges.append({
                'src_uid': src_uid,
                'tgt_uid': tgt_uid,
                'dep_label': dep.get("relation_subtype", ""),
                'confidence': dep["link_score"],
                'doc_id': doc_id,
            })
        else:
            # Marker-based → LEADS_TO with proper subtype
            all_action_edges.append({
                'src_uid': src_uid,
                'tgt_uid': tgt_uid,
                'relation_subtype': dep.get("relation_subtype") or "causes",
                'confidence': dep["link_score"],
                'evidence': [dep["marker_text"]] if dep["marker_text"] else [],
                'doc_id': doc_id,
                'status': 'pending',
            })

    logger.info(
        "[actions] total: %d action rows, %d LEADS_TO edges, %d SYNTACTIC_DEP edges",
        len(all_action_rows), len(all_action_edges), len(all_syntactic_edges)
    )

    # 5. Сохраняем узлы
    actions_count = action_repo.save_actions(all_action_rows, doc_id)

    # 6. Фильтруем LEADS_TO рёбра по DAG-правилу
    in_memory_neighbors: dict[str, List[str]] = {}

    def get_neighbors(uid: str) -> List[str]:
        try:
            persisted = action_repo.get_neighbor_ids(uid)
        except Exception:
            persisted = []
        return persisted + in_memory_neighbors.get(uid, [])

    dag_filtered_edges: List[dict] = []
    for edge in all_action_edges:
        src = edge['src_uid']
        tgt = edge['tgt_uid']
        if would_create_cycle(src, tgt, get_neighbors):
            logger.warning("Skipping edge %s→%s: would create cycle", src, tgt)
            continue
        dag_filtered_edges.append(edge)
        in_memory_neighbors.setdefault(src, []).append(tgt)

    edges_count = action_repo.save_leads_to(dag_filtered_edges, [], doc_id)
    pending_count = len(dag_filtered_edges)

    # 7. Сохраняем синтаксические зависимости (без DAG-проверки)
    if all_syntactic_edges:
        action_repo.save_syntactic_deps(all_syntactic_edges, doc_id)

    return ExtractActionsResult(
        actions_count=actions_count,
        edges_count=edges_count,
        pending_count=pending_count,
    )


def review_action_edge(
    doc_id: str,
    src_uid: str,
    tgt_uid: str,
    relation_subtype: str,
    decision: str,
    action_repo,
) -> None:
    """
    Подтверждает или отклоняет ребро.
    При decision='confirmed' проверяет DAG-правило (HTTP 409 если нарушает).
    """
    from domain.exceptions import ConflictError

    if decision == "confirmed":
        if would_create_cycle(src_uid, tgt_uid, action_repo.get_neighbor_ids):
            raise ConflictError(
                f"Cannot confirm edge {src_uid}→{tgt_uid}: would create a cycle"
            )

    action_repo.update_edge_status(src_uid, tgt_uid, relation_subtype, decision)

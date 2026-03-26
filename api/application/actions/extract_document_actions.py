"""
Layer: Application (Use Cases)
Package: application.actions.extract_document_actions
Responsibility: Извлечение действий и причинно-следственных цепочек из аннотаций документа.

Allowed imports: domain, application.ports, application.actions (extractors)
Forbidden imports: fastapi, neomodel, grpc, aioboto3, adapters, infrastructure, web
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import List

from domain.rules.graph_acyclicity import would_create_cycle
from domain.exceptions import NotFoundError

logger = logging.getLogger(__name__)

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
    import re

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

    # 3. Очистка при необходимости
    if clear_existing:
        action_repo.delete_for_document(doc_id)

    # 4. Один вызов NLP-сервиса на весь документ
    try:
        result = await nlp_client.extract_actions(full_text, doc_id=doc_id)
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
        all_action_rows.append({
            'uid': persistent_uid,
            'verb': a["verb_lemma"],
            'verb_text': a["verb_text"],
            'full_phrase': a["full_phrase"],
            'subject': None,
            'object': a["object_text"] or None,
            'sentence_text': a["sentence_text"],
            'char_start': a["char_start"],
            'char_end': a["char_end"],
            'doc_id': doc_id,
            'annotation_uid': None,
            'action_class': action_class,
        })

    # Build action→action edges
    for dep in nlp_deps:
        src_uid = uid_map.get(dep["source_id"])
        tgt_uid = uid_map.get(dep["target_id"])
        if not src_uid or not tgt_uid or src_uid == tgt_uid:
            continue
        all_action_edges.append({
            'src_uid': src_uid,
            'tgt_uid': tgt_uid,
            'relation_subtype': 'leads_to',
            'confidence': dep["link_score"],
            'evidence': [dep["marker_text"]] if dep["marker_text"] else [],
            'doc_id': doc_id,
            'status': 'pending',
        })

    logger.info(
        "[actions] total: %d action rows, %d action→action edges",
        len(all_action_rows), len(all_action_edges)
    )

    # 5. Сохраняем узлы
    actions_count = action_repo.save_actions(all_action_rows, doc_id)

    # 6. Фильтруем рёбра по DAG-правилу
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

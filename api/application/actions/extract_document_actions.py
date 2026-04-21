"""
Layer: Application (Use Cases)
Package: application.actions.extract_document_actions
Responsibility: Извлечение действий и причинно-следственных цепочек из аннотаций документа.

Allowed imports: domain, application.ports, application.actions (extractors)
Forbidden imports: fastapi, neomodel, grpc, aioboto3, adapters, infrastructure, web
"""
from __future__ import annotations

import asyncio
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


def _get_predecessors(uid: str, all_edges: List[dict]) -> List[str]:
    """Find all predecessors of a vertex (nodes that have edges pointing to this node)."""
    return [e['src_uid'] for e in all_edges if e['tgt_uid'] == uid]


def _get_successors(uid: str, all_edges: List[dict]) -> List[str]:
    """Find all successors of a vertex (nodes that this node points to)."""
    return [e['tgt_uid'] for e in all_edges if e['src_uid'] == uid]


def _create_action_copy(action_row: dict, new_uid: str) -> dict:
    """Create a deep copy of an action row with a new UID."""
    return {
        'uid': new_uid,
        'verb': action_row['verb'],
        'verb_text': action_row['verb_text'],
        'full_phrase': action_row['full_phrase'],
        'subject': action_row['subject'],
        'object': action_row['object'],
        'sentence_text': action_row['sentence_text'],
        'char_start': action_row['char_start'],
        'char_end': action_row['char_end'],
        'doc_id': action_row['doc_id'],
        'annotation_uid': action_row['annotation_uid'],
        'action_class': action_row['action_class'],
        'tokens': action_row.get('tokens', []),
        'spans': action_row.get('spans', []),
        'verb_span_idx': action_row.get('verb_span_idx', -1),
        'subject_span_idx': action_row.get('subject_span_idx', -1),
        'object_span_idx': action_row.get('object_span_idx', -1),
    }


def _split_cycle_and_expand_edges(
    src_uid: str,
    tgt_uid: str,
    edge_data: dict,
    action_rows: List[dict],
    all_edges: List[dict],
    new_action_rows: List[dict],
    new_edges: List[dict],
    uid_to_row: dict,
) -> None:
    """
    Split a cycle edge A→B by creating copies A' and B'.
    
    Original: A -x→ B, B -y→ A (cycle)
    Result:   A -x→ B', B' -y→ A' (no cycle)
    
    Additionally:
    - All predecessors P of A get edges P → B' (duplicate original P → A)
    - All successors S of B get edges A' → S (duplicate original B → S)
    """
    src_row = uid_to_row.get(src_uid)
    tgt_row = uid_to_row.get(tgt_uid)
    
    if not src_row or not tgt_row:
        return
    
    b_prime_uid = str(uuid.uuid4())
    a_prime_uid = str(uuid.uuid4())
    
    b_prime = _create_action_copy(tgt_row, b_prime_uid)
    a_prime = _create_action_copy(src_row, a_prime_uid)
    
    new_action_rows.append(b_prime)
    new_action_rows.append(a_prime)
    uid_to_row[b_prime_uid] = b_prime
    uid_to_row[a_prime_uid] = a_prime
    
    new_edges.append({
        'src_uid': src_uid,
        'tgt_uid': b_prime_uid,
        'relation_subtype': edge_data.get('relation_subtype', 'causes'),
        'confidence': edge_data.get('confidence', 0.5),
        'evidence': edge_data.get('evidence', []),
        'doc_id': edge_data['doc_id'],
        'status': edge_data.get('status', 'pending'),
    })
    
    reverse_edges = [e for e in all_edges if e['src_uid'] == tgt_uid and e['tgt_uid'] == src_uid]
    if reverse_edges:
        reverse_edge = reverse_edges[0]
        new_edges.append({
            'src_uid': b_prime_uid,
            'tgt_uid': a_prime_uid,
            'relation_subtype': reverse_edge.get('relation_subtype', 'causes'),
            'confidence': reverse_edge.get('confidence', 0.5),
            'evidence': reverse_edge.get('evidence', []),
            'doc_id': reverse_edge['doc_id'],
            'status': reverse_edge.get('status', 'pending'),
        })
    
    predecessors = _get_predecessors(src_uid, all_edges)
    for pred_uid in predecessors:
        pred_row = uid_to_row.get(pred_uid)
        if pred_row:
            new_edges.append({
                'src_uid': pred_uid,
                'tgt_uid': b_prime_uid,
                'relation_subtype': 'causes',
                'confidence': 0.5,
                'evidence': [],
                'doc_id': edge_data['doc_id'],
                'status': 'pending',
            })
    
    successors = _get_successors(tgt_uid, all_edges)
    for succ_uid in successors:
        succ_row = uid_to_row.get(succ_uid)
        if succ_row:
            new_edges.append({
                'src_uid': a_prime_uid,
                'tgt_uid': succ_uid,
                'relation_subtype': 'causes',
                'confidence': 0.5,
                'evidence': [],
                'doc_id': edge_data['doc_id'],
                'status': 'pending',
            })


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
    logger.info("[actions] doc=%s: starting", doc_id)
    
    # 1. Проверяем документ
    doc = document_repo.get_by_id(doc_id)
    if doc is None:
        logger.warning("[actions] doc=%s: document not found in repo", doc_id)
        raise NotFoundError("Document", doc_id)
    
    logger.info("[actions] doc=%s: found in repo, s3_bucket=%s", doc_id, doc.s3_bucket)

    # 2. Загружаем полный markdown текст
    key = doc.get_active_markdown_key()
    bucket = doc.s3_bucket

    if not key:
        logger.info("[actions] doc=%s: no active markdown key, trying fallback keys", doc_id)
        potential_keys = [
            f"documents/{doc_id}.md",
            f"pubmed/{doc_id}/{doc_id}.md",
            f"pubmed/{doc_id}/docling_raw.md",
            f"documents/{doc_id}/{doc_id}.md",
            f"markdown/{doc_id}_docling_raw.md",
            f"markdown/{doc_id}_formatted.md",
        ]
        for pk in potential_keys:
            exists = await storage.object_exists(bucket, pk)
            logger.info("[actions] doc=%s: checking key %s: exists=%s", doc_id, pk, exists)
            if exists:
                key = pk
                break

    if not key:
        logger.warning("[actions] doc=%s: no markdown key found", doc_id)
        raise NotFoundError("Document", doc_id)
    
    logger.info("[actions] doc=%s: found markdown key: %s", doc_id, key)
    full_text = await storage.download_text(bucket, key)
    if not full_text:
        logger.warning("[actions] doc=%s: markdown is empty", doc_id)
        raise NotFoundError("Document", doc_id)

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

    # 4. NLP — для больших текстов разбиваем на чанки по секциям (## Heading)
    CHUNK_LIMIT = 30_000  # символов; spaCy заметно замедляется выше этого порога

    chunks: List[Tuple[int, str]] = []  # (char_offset, chunk_text)
    if len(nlp_text) <= CHUNK_LIMIT:
        chunks = [(0, nlp_text)]
    else:
        # Разбиваем по заголовкам секций (## ...), сохраняя char offset
        section_starts = [0] + [m.start() for m in re.finditer(r'\n##+ ', nlp_text)]
        current_start = 0
        current_text = ""
        for i, sec_start in enumerate(section_starts):
            sec_end = section_starts[i + 1] if i + 1 < len(section_starts) else len(nlp_text)
            section = nlp_text[sec_start:sec_end]
            if len(current_text) + len(section) > CHUNK_LIMIT and current_text:
                chunks.append((current_start, current_text))
                current_start = sec_start
                current_text = section
            else:
                current_text += section
        if current_text:
            chunks.append((current_start, current_text))
        logger.info("[actions] doc=%s: split into %d chunks (text_len=%d)", doc_id, len(chunks), len(nlp_text))

    async def _extract_chunk(offset: int, chunk: str) -> Tuple[List[dict], List[dict]]:
        try:
            res = await nlp_client.extract_actions(chunk, doc_id=doc_id)
        except Exception as e:
            logger.error("[actions] NLP chunk error doc=%s offset=%d: %s", doc_id, offset, e)
            return [], []
        actions_raw = res.get("actions", [])
        deps_raw = res.get("dependencies", [])
        # Shift char positions by chunk offset
        for a in actions_raw:
            a["char_start"] += offset
            a["char_end"] += offset
            a["action_id"] = f"{offset}_{a['action_id']}"  # make globally unique
        for d in deps_raw:
            d["source_id"] = f"{offset}_{d['source_id']}"
            d["target_id"] = f"{offset}_{d['target_id']}"
        return actions_raw, deps_raw

    # Чанки обрабатываем последовательно, чтобы не перегружать NLP сервер
    # (параллельный gather при 11 чанках + фоновые аннотации → CANCELLED)
    chunk_results = []
    for off, ch in chunks:
        chunk_results.append(await _extract_chunk(off, ch))

    nlp_actions: List[dict] = []
    nlp_deps: List[dict] = []
    for acts, deps in chunk_results:
        nlp_actions.extend(acts)
        nlp_deps.extend(deps)

    logger.info("[actions] doc=%s: NLP returned %d actions, %d deps (from %d chunks)",
                doc_id, len(nlp_actions), len(nlp_deps), len(chunks))

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
            'subject': a.get("subject_text") or None,
            'object': a["object_text"] or None,
            'sentence_text': a["sentence_text"],
            'char_start': char_start,
            'char_end': char_end,
            'doc_id': doc_id,
            'annotation_uid': None,
            'action_class': action_class,
            # Лингвистические сущности
            'tokens': a.get("tokens") or [],
            'spans': a.get("spans") or [],
            'verb_span_idx': a.get("verb_span_idx", -1),
            'subject_span_idx': a.get("subject_span_idx", -1),
            'object_span_idx': a.get("object_span_idx", -1),
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
            # Marker-based and shared_entity → LEADS_TO with proper subtype
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

    # 5a. Анализ циклов и создание копий вершин для развёртывания
    # Строим маппинг uid → action_row для быстрого поиска
    uid_to_action_row: dict[str, dict] = {row['uid']: row for row in all_action_rows}
    
    # Ищем циклы в рёбрах и создаём копии вершин
    new_action_copies: List[dict] = []
    new_expanded_edges: List[dict] = []
    expanded_edge_uids: set = set()  # пары (src_uid, tgt_uid) которые уже развернули
    
    # Проверяем каждое ребро на возможность цикла
    edges_to_check = list(all_action_edges)
    checked_pairs: set = set()
    
    for edge in edges_to_check:
        src = edge['src_uid']
        tgt = edge['tgt_uid']
        pair_key = (src, tgt)
        
        if pair_key in checked_pairs:
            continue
        checked_pairs.add(pair_key)
        
        # Проверяем обратное ребро (tgt -> src)
        reverse_key = (tgt, src)
        has_reverse = any(
            e['src_uid'] == tgt and e['tgt_uid'] == src 
            for e in all_action_edges
        )
        
        if has_reverse and pair_key not in expanded_edge_uids:
            # Нашли цикл A -> B и B -> A, разворачиваем его
            _split_cycle_and_expand_edges(
                src_uid=src,
                tgt_uid=tgt,
                edge_data=edge,
                action_rows=all_action_rows,
                all_edges=all_action_edges,
                new_action_rows=new_action_copies,
                new_edges=new_expanded_edges,
                uid_to_row=uid_to_action_row,
            )
            expanded_edge_uids.add(pair_key)
            expanded_edge_uids.add(reverse_key)
    
    if new_action_copies:
        logger.info(
            "[actions] doc=%s: expanded %d cycles -> created %d action copies, %d new edges",
            doc_id, len(expanded_edge_uids) // 2, len(new_action_copies), len(new_expanded_edges)
        )
        # Добавляем копии к оригинальным вершинам
        all_action_rows.extend(new_action_copies)
    
    # 5b. Сохраняем узлы, получаем uid_remap для дедупликации
    uid_remap = action_repo.save_actions(all_action_rows, doc_id)
    actions_count = len(set(uid_remap.values())) if isinstance(uid_remap, dict) else uid_remap

    # Remap edge uids to actual (deduplicated) uids
    if isinstance(uid_remap, dict):
        for edge in all_action_edges:
            edge['src_uid'] = uid_remap.get(edge['src_uid'], edge['src_uid'])
            edge['tgt_uid'] = uid_remap.get(edge['tgt_uid'], edge['tgt_uid'])
        for edge in all_syntactic_edges:
            edge['src_uid'] = uid_remap.get(edge['src_uid'], edge['src_uid'])
            edge['tgt_uid'] = uid_remap.get(edge['tgt_uid'], edge['tgt_uid'])
        # Also remap the newly expanded edges from cycle splitting
        for edge in new_expanded_edges:
            edge['src_uid'] = uid_remap.get(edge['src_uid'], edge['src_uid'])
            edge['tgt_uid'] = uid_remap.get(edge['tgt_uid'], edge['tgt_uid'])
    
    # Combine original edges with expanded edges (from cycle splitting)
    all_leads_to_edges = list(all_action_edges) + list(new_expanded_edges)

    # 6. Фильтруем LEADS_TO рёбра по DAG-правилу
    # Загружаем все существующие рёбра документа один раз — O(1) Neo4j запрос
    # вместо O(E×V) запросов при BFS через get_neighbor_ids
    try:
        existing_edges = action_repo.get_all_edges_for_document(doc_id)
    except Exception:
        existing_edges = []
    persisted_neighbors: dict[str, List[str]] = {}
    for src, tgt in existing_edges:
        persisted_neighbors.setdefault(src, []).append(tgt)

    in_memory_neighbors: dict[str, List[str]] = {}

    def get_neighbors(uid: str) -> List[str]:
        return list(persisted_neighbors.get(uid, [])) + in_memory_neighbors.get(uid, [])

    dag_filtered_edges: List[dict] = []
    cycle_skipped = 0
    for edge in all_leads_to_edges:
        src = edge['src_uid']
        tgt = edge['tgt_uid']
        if would_create_cycle(src, tgt, get_neighbors):
            cycle_skipped += 1
            continue
        dag_filtered_edges.append(edge)
        in_memory_neighbors.setdefault(src, []).append(tgt)

    if cycle_skipped:
        logger.info("[actions] doc=%s: still has %d cycle-forming edges (fallback)", doc_id, cycle_skipped)

    edges_count = action_repo.save_leads_to(dag_filtered_edges, doc_id)
    pending_count = len(dag_filtered_edges)
    
    logger.info(
        "[actions] doc=%s: saved actions_count=%d, edges_count=%d, pending_count=%d",
        doc_id, actions_count, edges_count, pending_count
    )

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

"""
Layer: Application (Use Cases)
Package: application.patterns.analyze_document_patterns
Responsibility: Анализ лингвистических паттернов в аннотациях документа.

Извлекает паттерны из текстов аннотаций через NLP-сервис и сохраняет их в Neo4j.

Allowed imports: typing, collections, dataclasses, domain.*, application.ports.*
Forbidden imports: neomodel, fastapi, grpc, aioboto3, infrastructure, adapters, web
"""
from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from domain.exceptions import NotFoundError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dataclasses результата (чистые, без ORM)
# ---------------------------------------------------------------------------

@dataclass
class PatternRow:
    pattern_str: str
    pattern_type: str
    frequency: int


@dataclass
class AnnotationTypePatterns:
    annotation_type: str
    patterns: List[PatternRow]
    total_annotations: int


# ---------------------------------------------------------------------------
# Извлечение паттернов из NLP-результата
# ---------------------------------------------------------------------------

def _extract_patterns(
    nlp_doc: Dict[str, Any],
    annotation_type: str,
    annotation_uid: str,
    doc_id: str,
) -> List[Dict[str, Any]]:
    """Извлекает 5 типов паттернов из UnifiedDocument (словарь от NLP-клиента)."""
    results: List[Dict[str, Any]] = []

    for sent in nlp_doc.get("sentences", []):
        tokens: List[Dict] = sent.get("tokens", [])
        deps: List[Dict] = sent.get("dependencies", [])

        # Индекс токенов по idx
        token_by_idx: Dict[int, Dict] = {t["idx"]: t for t in tokens}

        # --- pos_sequence ---
        pos_tags = [
            t["pos"] for t in tokens
            if not t.get("is_punct") and not t.get("is_space") and t.get("pos")
        ]
        if pos_tags:
            results.append(_make_row(
                pattern_str=" ".join(pos_tags),
                pattern_type="pos_sequence",
                annotation_type=annotation_type,
                annotation_uid=annotation_uid,
                doc_id=doc_id,
            ))

        # --- dep_bigram / dep_trigram ---
        dep_rels = [d["relation"] for d in deps if d.get("relation")]
        for i in range(len(dep_rels) - 1):
            results.append(_make_row(
                pattern_str=f"{dep_rels[i]}→{dep_rels[i+1]}",
                pattern_type="dep_bigram",
                annotation_type=annotation_type,
                annotation_uid=annotation_uid,
                doc_id=doc_id,
            ))
        for i in range(len(dep_rels) - 2):
            results.append(_make_row(
                pattern_str=f"{dep_rels[i]}→{dep_rels[i+1]}→{dep_rels[i+2]}",
                pattern_type="dep_trigram",
                annotation_type=annotation_type,
                annotation_uid=annotation_uid,
                doc_id=doc_id,
            ))

        # --- token_dep_pair  и  head_dep_chain ---
        for dep in deps:
            rel = dep.get("relation")
            dep_idx = dep.get("dependent_idx")
            head_idx = dep.get("head_idx")
            if rel is None or dep_idx is None or head_idx is None:
                continue

            dep_tok = token_by_idx.get(dep_idx)
            head_tok = token_by_idx.get(head_idx)

            if dep_tok and dep_tok.get("pos"):
                # Формат как в ноутбуке: "word/POS (dep) -> head"
                head_text = head_tok["text"].lower() if head_tok else "?"
                results.append(_make_row(
                    pattern_str=f"{dep_tok['text'].lower()}/{dep_tok['pos']} ({rel}) -> {head_text}",
                    pattern_type="token_dep_pair",
                    annotation_type=annotation_type,
                    annotation_uid=annotation_uid,
                    doc_id=doc_id,
                ))

            if dep_tok and head_tok and dep_tok.get("pos") and head_tok.get("pos"):
                results.append(_make_row(
                    pattern_str=(
                        f"{head_tok['text']}/{head_tok['pos']} "
                        f"→[{rel}]→ "
                        f"{dep_tok['text']}/{dep_tok['pos']}"
                    ),
                    pattern_type="head_dep_chain",
                    annotation_type=annotation_type,
                    annotation_uid=annotation_uid,
                    doc_id=doc_id,
                ))

    return results


def _make_row(
    pattern_str: str,
    pattern_type: str,
    annotation_type: str,
    annotation_uid: str,
    doc_id: str,
) -> Dict[str, Any]:
    return {
        "pattern_str": pattern_str,
        "pattern_type": pattern_type,
        "annotation_type": annotation_type,
        "annotation_uid": annotation_uid,
        "doc_id": doc_id,
        "frequency": 1,
    }


# ---------------------------------------------------------------------------
# Use Case
# ---------------------------------------------------------------------------

async def analyze_document_patterns(
    annotation_repo: Any,
    document_repo: Any,
    pattern_repo: Any,
    nlp_client: Any,
    doc_id: str,
    annotation_types: Optional[List[str]] = None,
    clear_existing: bool = True,
    min_frequency: int = 1,
) -> List[AnnotationTypePatterns]:
    """
    Анализирует лингвистические паттерны в аннотациях документа.

    1. Проверяет существование документа.
    2. Загружает аннотации нужных типов.
    3. Для каждой аннотации вызывает NLP-сервис (syntax level).
    4. Агрегирует частоты паттернов.
    5. Сохраняет в Neo4j через pattern_repo.
    6. Возвращает таблицы по 4 типам аннотаций.
    """
    _GOAL_TYPES = [
        "Успешная цель",
        "Не успешная цель",
        "Фрагмент ведёт к успеху",
        "Фрагмент ведёт к неуспеху",
    ]

    if annotation_types is None:
        annotation_types = _GOAL_TYPES

    # Проверяем документ
    doc = document_repo.get_by_id(doc_id)
    if doc is None:
        raise NotFoundError("PDFDocument", doc_id)

    # Загружаем аннотации нужных типов
    annotations, _ = annotation_repo.get_by_document(
        doc_id,
        skip=0,
        limit=None,
        annotation_types=annotation_types,
    )

    if clear_existing:
        pattern_repo.delete_for_document(doc_id)

    # Собираем все паттерны со счётчиком
    # Ключ агрегации — без annotation_uid, чтобы считать частоту по всему документу
    counter: Counter = Counter()
    # Дополнительно храним первый annotation_uid для каждого уникального паттерна
    first_uid: Dict[tuple, str] = {}

    all_rows: List[Dict[str, Any]] = []

    for ann in annotations:
        if not ann.text or not ann.text.strip():
            continue
        try:
            # enable_voting=False, min_agreement=1 — у нас только spaCy
            nlp_response = await nlp_client.analyze_text(
                ann.text,
                levels=["syntax"],
                enable_voting=False,
                min_agreement=1,
            )
        except Exception as e:
            logger.warning(f"[analyze_patterns] NLP-ошибка для аннотации {ann.uid}: {e}")
            continue

        # analyze_text возвращает {"success": ..., "document": {...}, ...}
        # sentences находятся внутри document
        nlp_doc = nlp_response.get("document") or {}
        sentences = nlp_doc.get("sentences", [])
        first_sent_deps = len(sentences[0].get("dependencies", [])) if sentences else 0
        first_sent_tokens = len(sentences[0].get("tokens", [])) if sentences else 0
        logger.info(
            f"[analyze_patterns] ann={ann.uid[:8]} type={ann.annotation_type!r} "
            f"text_len={len(ann.text)} sentences={len(sentences)} "
            f"tokens={first_sent_tokens} deps={first_sent_deps}"
        )

        rows = _extract_patterns(
            nlp_doc=nlp_doc,
            annotation_type=ann.annotation_type,
            annotation_uid=ann.uid,
            doc_id=doc_id,
        )
        logger.info(f"[analyze_patterns] extracted {len(rows)} raw patterns from ann={ann.uid[:8]}")

        for row in rows:
            key = (row["pattern_str"], row["pattern_type"], row["annotation_type"])
            counter[key] += 1
            if key not in first_uid:
                first_uid[key] = row["annotation_uid"]

    # Формируем итоговый список с агрегированными частотами
    aggregated: List[Dict[str, Any]] = []
    for (pattern_str, pattern_type, annotation_type), freq in counter.items():
        if freq < min_frequency:
            continue
        aggregated.append({
            "pattern_str": pattern_str,
            "pattern_type": pattern_type,
            "annotation_type": annotation_type,
            "frequency": freq,
            "doc_id": doc_id,
            "annotation_uid": first_uid[(pattern_str, pattern_type, annotation_type)],
        })

    logger.info(
        f"[analyze_patterns] doc={doc_id[:8]} annotations={len(annotations)} "
        f"aggregated_patterns={len(aggregated)}"
    )

    # Сохраняем в Neo4j
    if aggregated:
        pattern_repo.save_patterns(aggregated, doc_id)

    # Группируем по annotation_type для ответа
    # Счётчик аннотаций по типу
    ann_type_count: Dict[str, int] = {}
    for ann in annotations:
        ann_type_count[ann.annotation_type] = ann_type_count.get(ann.annotation_type, 0) + 1

    groups: Dict[str, List[PatternRow]] = {t: [] for t in annotation_types}
    for row in aggregated:
        at = row["annotation_type"]
        if at in groups:
            groups[at].append(PatternRow(
                pattern_str=row["pattern_str"],
                pattern_type=row["pattern_type"],
                frequency=row["frequency"],
            ))

    # Сортируем каждую группу по убыванию частоты
    result: List[AnnotationTypePatterns] = []
    for at in annotation_types:
        patterns = sorted(groups.get(at, []), key=lambda r: r.frequency, reverse=True)
        result.append(AnnotationTypePatterns(
            annotation_type=at,
            patterns=patterns,
            total_annotations=ann_type_count.get(at, 0),
        ))

    return result

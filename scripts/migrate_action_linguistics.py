"""
Миграция: генерация лингвистических структур и LexicalUnit из существующих Action-нод.

Для каждой Action-ноды в Neo4j:
1. Берёт sentence_text
2. Прогоняет через spaCy → извлекает токены, строит DependencySpan'ы
3. Находит verb/subject/object по lemma/dep (обратный инжиниринг)
4. Сериализует в tokens_json / spans_json
5. Создаёт LexicalUnit ноды + рёбра DEPENDS_ON
6. Вычисляет label_text
7. Сохраняет новые поля

Запуск:
    poetry run python scripts/migrate_action_linguistics.py [--force] [--batch-size 1000]
    poetry run python scripts/migrate_action_linguistics.py --lexical-only  # только LexicalUnit
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import uuid as _uuid
from pathlib import Path


def _uuid8_str() -> str:
    ts_us = int(time.time() * 1_000_000)
    rand = os.urandom(7)
    b = bytearray(16)
    for i in range(8):
        b[i] = (ts_us >> (56 - i * 8)) & 0xFF
    b[6] = (b[6] & 0x0F) | 0x80
    b[8] = 0x80 | (rand[0] & 0x3F)
    b[9:16] = rand[:]
    return str(_uuid.UUID(bytes=bytes(b)))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Добавляем корень проекта в sys.path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Загружаем конфигурацию Neo4j из .env
import os
os.chdir(str(project_root))  # чтобы .env нашёлся относительно корня

from neomodel import db, config
from api.infrastructure.config import settings

config.DATABASE_URL = settings.get_database_url()
logger.info("Neo4j: %s", settings.NEO4J_URI)

import spacy

DEFAULT_BATCH_SIZE = 1000


def _build_span_from_token(token, span_type: str) -> dict:
    """Строит DependencySpan dict из spaCy токена."""
    subtree = list(token.subtree)
    return {
        "span_type": span_type,
        "token_ids": [t.i for t in subtree],
        "head_token_id": token.i,
        "text": token.doc[subtree[0].i: subtree[-1].i + 1].text,
        "lemma_form": token.lemma_.lower(),
    }


def _find_verb_token(doc, verb_lemma: str, verb_text: str):
    """Находит токен глагола в doc по лемме и тексту."""
    for token in doc:
        if token.pos_ in ('VERB', 'AUX'):
            if token.lemma_.lower() == verb_lemma.lower():
                return token
            if token.text.lower() == verb_text.lower():
                return token
    for token in doc:
        if token.pos_ in ('VERB', 'AUX'):
            return token
    return None


def _find_object_span(verb_token):
    """Находит object NP по зависимостям от глагола."""
    if not verb_token:
        return None
    for child in verb_token.children:
        if child.dep_ in ('obj', 'dobj', 'nsubj:pass', 'obl'):
            cut_i = None
            for grandchild in child.children:
                if grandchild.dep_ in ('relcl', 'acl', 'acl:relcl', 'appos'):
                    cut_i = grandchild.left_edge.i
                    break
            if cut_i is not None:
                span_tokens = [t for t in child.subtree if t.i < cut_i]
                while span_tokens and span_tokens[-1].is_punct:
                    span_tokens.pop()
                if span_tokens:
                    return {
                        "span_type": "OBJECT",
                        "token_ids": [t.i for t in span_tokens],
                        "head_token_id": child.i,
                        "text": child.doc[span_tokens[0].i: span_tokens[-1].i + 1].text,
                        "lemma_form": child.lemma_.lower(),
                    }
            return _build_span_from_token(child, "OBJECT")
    return None


def _find_subject_span(verb_token):
    """Находит subject NP по зависимостям от глагола."""
    if not verb_token:
        return None
    for child in verb_token.children:
        if child.dep_ in ('nsubj', 'nsubj:pass', 'nsubjpass'):
            return _build_span_from_token(child, "SUBJECT")
    head = verb_token.head
    if head != verb_token and head.pos_ in ('VERB', 'AUX'):
        for child in head.children:
            if child.dep_ in ('nsubj', 'nsubj:pass', 'nsubjpass'):
                return _build_span_from_token(child, "SUBJECT")
    return None


def process_action(nlp, action: dict) -> dict | None:
    """Обрабатывает одну Action-ноду: генерирует tokens_json, spans_json, label_text,
    а также данные для LexicalUnit."""
    uid = action.get("uid")
    sentence_text = action.get("sentence_text")
    verb_lemma = action.get("verb", "")
    verb_text = action.get("verb_text", "")
    subject = action.get("subject", "")
    obj = action.get("object", "")
    doc_id = action.get("doc_id", "")

    if not sentence_text:
        logger.warning("Action %s: нет sentence_text, пропускаю", uid)
        return None

    doc = nlp(sentence_text)

    # Собираем все токены
    tokens = [
        {
            "id": t.i,
            "text": t.text,
            "lemma": t.lemma_,
            "pos": t.pos_,
            "pos_fine": t.tag_,
            "dep": t.dep_,
            "head_id": t.head.i,
            "is_stop": t.is_stop,
            "is_punct": t.is_punct,
        }
        for t in doc
    ]

    # Находим глагол
    verb_token = _find_verb_token(doc, verb_lemma, verb_text)
    verb_span = _build_span_from_token(verb_token, "VERB") if verb_token else None

    # Находим subject и object
    subject_span = _find_subject_span(verb_token)
    object_span = _find_object_span(verb_token)

    # Собираем spans
    spans = []
    verb_span_idx = -1
    subject_span_idx = -1
    object_span_idx = -1

    if verb_span:
        verb_span_idx = len(spans)
        spans.append(verb_span)

    if verb_token:
        for child in verb_token.children:
            if child.dep_ in ('amod', 'advmod', 'neg', 'prt'):
                spans.append(_build_span_from_token(child, "MODIFIER"))

    if subject_span:
        subject_span_idx = len(spans)
        spans.append(subject_span)

    if object_span:
        object_span_idx = len(spans)
        spans.append(object_span)

    # Рендерим label_text
    parts = []
    if subject_span:
        parts.append(subject_span["text"])
    if verb_span:
        parts.append(verb_span["text"])
    if object_span:
        parts.append(object_span["text"])
    label_text = " ".join(parts) if parts else f"{verb_text} {obj}".strip()

    # Генерируем LexicalUnit данные
    token_id_to_lu_uid: dict[int, str] = {}
    lexical_units: list[dict] = []
    dependency_edges: list[dict] = []

    for token in tokens:
        lu_uid = _uuid8_str()
        token_id_to_lu_uid[token["id"]] = lu_uid

        lexical_units.append({
            "uid": lu_uid,
            "text": token["text"],
            "lemma": token["lemma"],
            "pos": token["pos"],
            "pos_fine": token["pos_fine"],
            "dep": token["dep"],
            "is_stop": token["is_stop"],
            "is_punct": token["is_punct"],
            "doc_id": doc_id,
            "action_uid": uid,
            "token_index": token["id"],
        })

    # Рёбра DEPENDS_ON
    for token in tokens:
        head_id = token.get("head_id", -1)
        if head_id < 0:
            continue
        src_uid = token_id_to_lu_uid.get(head_id)
        tgt_uid = token_id_to_lu_uid.get(token["id"])
        if src_uid and tgt_uid and src_uid != tgt_uid:
            dependency_edges.append({
                "src_uid": src_uid,
                "tgt_uid": tgt_uid,
                "dep_label": token["dep"],
                "doc_id": doc_id,
            })

    return {
        "uid": uid,
        "tokens_json": json.dumps(tokens, ensure_ascii=False),
        "spans_json": json.dumps(spans, ensure_ascii=False),
        "label_text": label_text,
        "verb_span_idx": verb_span_idx,
        "subject_span_idx": subject_span_idx,
        "object_span_idx": object_span_idx,
        # LexicalUnit данные
        "lexical_units": lexical_units,
        "dependency_edges": dependency_edges,
    }


def migrate(
    force: bool = False,
    batch_size: int = DEFAULT_BATCH_SIZE,
    lexical_only: bool = False,
    model_name: str = "en_core_web_sm",
) -> int:
    """Запускает миграцию всех Action-нод."""
    logger.info("Загрузка spaCy модели '%s'...", model_name)
    try:
        nlp = spacy.load(model_name)
    except OSError:
        # Fallback: попробовать модель из NLP окружения
        fallback_path = Path(__file__).parent.parent / "nlp" / ".venv" / "lib" / "site-packages" / "en_core_sci_scibert" / "en_core_sci_scibert-0.5.4"
        if fallback_path.exists():
            logger.info("Falling back to NLP venv model: %s", fallback_path)
            nlp = spacy.load(str(fallback_path))
        else:
            logger.error("Модель '%s' не найдена. Установите: python -m spacy download en_core_web_sm", model_name)
            return 0

    # Считаем总量
    count_res, _ = db.cypher_query("MATCH (a:Action) RETURN count(a) AS cnt")
    total = int(count_res[0][0]) if count_res else 0
    logger.info("Всего Action-нод: %d", total)

    if total == 0:
        return 0

    # Загружаем ноды
    if lexical_only:
        # Только LexicalUnit — нужны все Action, даже если tokens_json заполнен
        query = """
        MATCH (a:Action)
        RETURN a.uid AS uid, a.verb AS verb, a.verb_text AS verb_text,
               a.subject AS subject, a.object AS object,
               a.sentence_text AS sentence_text, a.doc_id AS doc_id
        """
    elif force:
        query = """
        MATCH (a:Action)
        RETURN a.uid AS uid, a.verb AS verb, a.verb_text AS verb_text,
               a.subject AS subject, a.object AS object,
               a.sentence_text AS sentence_text, a.doc_id AS doc_id
        """
    else:
        query = """
        MATCH (a:Action) WHERE a.tokens_json IS NULL
        RETURN a.uid AS uid, a.verb AS verb, a.verb_text AS verb_text,
               a.subject AS subject, a.object AS object,
               a.sentence_text AS sentence_text, a.doc_id AS doc_id
        """

    results, _ = db.cypher_query(query)
    actions = [
        {
            "uid": r[0],
            "verb": r[1] or "",
            "verb_text": r[2] or "",
            "subject": r[3] or "",
            "object": r[4] or "",
            "sentence_text": r[5] or "",
            "doc_id": r[6] or "",
        }
        for r in results
    ]

    if not actions:
        logger.info("Все ноды уже мигрированы (tokens_json заполнен)")
        return 0

    logger.info("Миграция %d нод...", len(actions))

    total_lu_nodes = 0
    total_dep_edges = 0
    updated_actions = 0
    errors = 0

    for i in range(0, len(actions), batch_size):
        batch = actions[i:i + batch_size]
        logger.info("Пакет %d-%d из %d...", i, min(i + batch_size, len(actions)), len(actions))

        update_rows = []
        all_lu_rows: list[dict] = []
        all_dep_rows: list[dict] = []

        for action in batch:
            try:
                result = process_action(nlp, action)
                if result:
                    update_rows.append(result)
                    all_lu_rows.extend(result["lexical_units"])
                    all_dep_rows.extend(result["dependency_edges"])
            except Exception as e:
                logger.error("Ошибка обработки Action %s: %s", action.get("uid"), e, exc_info=True)
                errors += 1

        # Сохраняем Action обновления
        if update_rows and not lexical_only:
            update_query = """
            UNWIND $rows AS row
            MATCH (a:Action {uid: row.uid})
            SET a.tokens_json = row.tokens_json,
                a.spans_json = row.spans_json,
                a.label_text = row.label_text,
                a.verb_span_idx = row.verb_span_idx,
                a.subject_span_idx = row.subject_span_idx,
                a.object_span_idx = row.object_span_idx
            """
            db.cypher_query(update_query, {"rows": update_rows})
            updated_actions += len(update_rows)

        # Сохраняем LexicalUnit ноды
        if all_lu_rows:
            lu_query = """
            UNWIND $rows AS row
            MERGE (lu:LexicalUnit {uid: row.uid})
            ON CREATE SET
                lu.text     = row.text,
                lu.lemma    = row.lemma,
                lu.pos      = row.pos,
                lu.pos_fine = row.pos_fine,
                lu.dep      = row.dep,
                lu.is_stop  = row.is_stop,
                lu.is_punct = row.is_punct,
                lu.doc_id   = row.doc_id
            ON MATCH SET
                lu.text     = row.text,
                lu.lemma    = row.lemma,
                lu.pos      = row.pos,
                lu.dep      = row.dep
            WITH lu, row
            MATCH (a:Action {uid: row.action_uid})
            MERGE (lu)-[r:PART_OF {doc_id: row.doc_id}]->(a)
            ON CREATE SET r.token_index = row.token_index
            """
            db.cypher_query(lu_query, {"rows": all_lu_rows})
            total_lu_nodes += len(all_lu_rows)

        # Сохраняем рёбра DEPENDS_ON
        if all_dep_rows:
            dep_query = """
            UNWIND $rows AS row
            MATCH (src:LexicalUnit {uid: row.src_uid}), (tgt:LexicalUnit {uid: row.tgt_uid})
            MERGE (src)-[r:DEPENDS_ON {doc_id: row.doc_id, dep_label: row.dep_label}]->(tgt)
            """
            db.cypher_query(dep_query, {"rows": all_dep_rows})
            total_dep_edges += len(all_dep_rows)

        logger.info(
            "Сохранено: actions=%d, LU=%d, edges=%d (ошибок: %d)",
            updated_actions, total_lu_nodes, total_dep_edges, errors,
        )

    logger.info(
        "Миграция заверена. Actions: %d, LexicalUnit: %d, DEPENDS_ON: %d, Ошибок: %d",
        updated_actions, total_lu_nodes, total_dep_edges, errors,
    )
    return total_lu_nodes


def main():
    parser = argparse.ArgumentParser(
        description="Миграция Action-нод: генерация лингвистических структур + LexicalUnit"
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Перевычислить все ноды (даже если tokens_json уже заполнен)"
    )
    parser.add_argument(
        "--batch-size", type=int, default=DEFAULT_BATCH_SIZE,
        help="Размер пакета (по умолчанию 1000)"
    )
    parser.add_argument(
        "--lexical-only", action="store_true",
        help="Создать только LexicalUnit ноды (без обновления tokens_json/spans_json)"
    )
    parser.add_argument(
        "--model", type=str, default="en_core_web_sm",
        help="Имя spaCy модели (по умолчанию en_core_web_sm)"
    )
    args = parser.parse_args()

    count = migrate(force=args.force, batch_size=args.batch_size, lexical_only=args.lexical_only, model_name=args.model)
    print(f"Создано {count} LexicalUnit нод")


if __name__ == "__main__":
    main()

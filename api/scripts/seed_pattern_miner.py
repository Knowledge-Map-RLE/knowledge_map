# -*- coding: utf-8 -*-
"""
Генератор синтетического корпуса для проверки алгоритма выявления паттернов
(pattern-miner) «как будто» в базе много статей и утверждений.

Создаёт N синтетических документов, каждый с AST-деревом утверждений,
построенным из «шаблонов» импликаций:
  * цепочки импликаций (concept -[increases]-> concept -> ...),
  * ветвления (один субъект, несколько объектов/предикатов),
  * вложенные утверждения (subject_type/object_type == 'statement',
    subject_text/object_text == uid внутреннего утверждения),
  * литералы как объекты.

Тексты концептов рандомизируются для каждой статьи, но топология (метки рёбер
и типы узлов) внутри семейства одинакова — поэтому частотный майнинг находит
сложные структурные паттерны, а не «конкретные цепочки слов».

Usage:
    python scripts/seed_pattern_miner.py --docs 200 --clear

Созданные документы помечаются свойством synthetic=true и именуются
[SYNTH] ... — их можно удалить ключом --clear.
"""
# Этим компонентом удобно проверять и СТРУКТУРНЫЙ майнинг (паттерны), и
# ГЕНЕРАЦИЮ нового знания четырьмя способами (logical/syllogism/thinking).
#
# Для структурного майнинга нужен корпус с рандомизированными концептами
# (топология важнее текста): --docs создаёт такие документы.
#
# Для генерации знания важны *осмысленные тексты* и категориальные цепочки
# (is_a/include/be) + причинно-следственные связи. Такие документы создаёт
# --semantic-docs, семантический корпус `synth-pm-sem-*`.
from __future__ import annotations

import argparse
import random
import sys
from typing import Any, Dict, List

from neomodel import config as neo_config, db
from infrastructure.config import settings
from src.uuid8 import uuid8_str

neo_config.DATABASE_URL = settings.get_database_url()

CONCEPT_POOL_A = "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu".split()
CONCEPT_POOL_B = "renin cortisol insulin glucemia erythema mycosis plaque".split()
LITERAL_POOL = ["elevated", "decreased", "normal", "absent", "3.2-fold"].copy()

# ── Семантический корпус: реалистичные концепты для 4 способов генерации ──
SEM_CATEGORIES = {
    "hallmarks of aging": ["mitochondrial dysfunction", "telomere shortening",
                           "epigenetic alterations", "loss of proteostasis",
                           "cellular senescence"],
    "pillars of aging": ["molecular hallmarks", "cellular hallmarks",
                         "systemic hallmarks"],
    "essential nutrient": ["vitamin D", "vitamin C"],
    "chronic disease": ["type 2 diabetes", "cardiovascular disease"],
    "hallmark processes": ["immunosenescence", "inflammaging"],
}
SEM_CAUSAL = [
    ("aging", "leads to", "immunosenescence"),
    ("aging", "causes", "inflammaging"),
    ("immunosenescence", "increases", "susceptibility to infection"),
    ("immunosenescence", "contributes to", "thymic involution"),
    ("telomere shortening", "activates", "cellular senescence"),
    ("cellular senescence", "secrets", "senescence-associated secretory phenotype"),
    ("senescence-associated secretory phenotype", "promotes", "chronic inflammation"),
    ("chronic inflammation", "increases", "cardiovascular disease"),
    ("vitamin D", "regulates", "immune system"),
    ("vitamin D", "decreases", "inflammation"),
    ("vitamin D", "activates", "macrophages"),
    ("aging", "leads to", "decline in T cell function"),
]
SEM_CAT_EDGES = [
    ("mitochondrial dysfunction", "be", "hallmarks of aging"),
    ("telomere shortening", "be", "hallmarks of aging"),
    ("epigenetic alterations", "be", "hallmarks of aging"),
    ("loss of proteostasis", "be", "hallmarks of aging"),
    ("cellular senescence", "be", "hallmarks of aging"),
    ("hallmarks of aging", "be", "pillars of aging"),
    ("vitamin D", "be", "essential nutrient"),
    ("vitamin C", "be", "essential nutrient"),
    ("type 2 diabetes", "is_a", "chronic disease"),
    ("cardiovascular disease", "is_a", "chronic disease"),
    ("immunosenescence", "is_a", "hallmark processes"),
    ("inflammaging", "is_a", "hallmark processes"),
]


def build_semantic_document(doc_uid: str, rng: random.Random) -> List[Dict[str, Any]]:
    """Один документ семантического корпуса: категориальные + причинные связи.

    Берём подмножество (≈60%) категорий и причинных связей, чтобы в корпусе
    была вариативность (паттерны на семантике тоже ищутся), а тексты остались
    осмысленными для syllogism/thinking.
    """
    n_cat = max(3, int(len(SEM_CAT_EDGES) * 0.6))
    cat_rows = rng.sample(SEM_CAT_EDGES, n_cat)
    n_caus = max(4, int(len(SEM_CAUSAL) * 0.65))
    caus_rows = rng.sample(SEM_CAUSAL, n_caus)
    rows: List[Dict[str, Any]] = []
    order = 0
    for subj, pred, obj in cat_rows + caus_rows:
        rows.append({
            "uid": uuid8_str(),
            "subject_text": subj,
            "predicate": pred,
            "object_text": obj,
            "subject_type": "concept",
            "object_type": "concept",
            "type": "FACT",
            "confidence": round(rng.uniform(0.85, 0.99), 3),
            "sort_order": order,
        })
        order += 1
    # разбавляем статистическим шумом (паттерны pattern-способа тоже дают сигнал)
    extra = rng.randint(2, 4)
    for _ in range(extra):
        s = rng.choice(list(SEM_CATEGORIES) + [c for chain in SEM_CATEGORIES.values() for c in chain])
        rows.append({
            "uid": uuid8_str(),
            "subject_text": s,
            "predicate": rng.choice(["correlates with", "affects", "modulates"]),
            "object_text": rng.choice(list(SEM_CATEGORIES)),
            "subject_type": "concept",
            "object_type": "concept",
            "type": "FACT",
            "confidence": round(rng.uniform(0.6, 0.9), 3),
            "sort_order": order,
        })
        order += 1
    for r in rows:
        r.setdefault("created_by_uid", "synth-pattern-miner")
    return rows


def create_semantic_corpus(num_docs: int, rng: random.Random) -> None:
    print(f"Создаю {num_docs} семантических документов (для генерации знания)…")
    for i in range(num_docs):
        doc_uid = f"synth-pm-sem-{i:05d}"
        title = f"[SYNTH] km-sem-{i:05d}"
        rows = build_semantic_document(doc_uid, rng)
        db.cypher_query(
            "MERGE (d:Document {uid: $doc_uid}) "
            "SET d.original_filename = $title, d.md5_hash = $doc_uid, d.s3_key = '', "
            "d.title = $title, d.processing_status = 'ready_for_annotation', "
            "d.is_processed = true, d.created_by_uid = 'synth-pattern-miner', d.synthetic = true",
            {"doc_uid": doc_uid, "title": title},
        )
        for chunk_start in range(0, len(rows), 500):
            chunk = rows[chunk_start:chunk_start + 500]
            db.cypher_query(
                "MATCH (d:Document {uid: $doc_uid}) "
                "UNWIND $batch AS item "
                "CREATE (s:KnowledgeStatement {uid: item.uid, subject_text: item.subject_text, "
                "predicate: item.predicate, object_text: item.object_text, "
                "subject_type: item.subject_type, object_type: item.object_type, "
                "type: item.type, confidence: item.confidence, sentence_text: '', "
                "sort_order: item.sort_order, created_by_uid: item.created_by_uid}) "
                "CREATE (d)-[:HAS_STATEMENT]->(s)",
                {"doc_uid": doc_uid, "batch": chunk},
            )
        if i % 50 == 0:
            print(f"  …{i}")
    print("Готово (семантический корпус).")


def norm_concept(pool: List[str], rng: random.Random) -> str:
    return f"{rng.choice(pool)}-{rng.randint(1, 999)}"


# Каждый шаблон — список «слотов» утверждений.
# Слот: (subject_kind, predicate, object_kind), subject_kind/object_kind:
#   'concept' | 'literal' | int (индекс слота, на который ссылаемся как на
#   вложенное утверждение). Объект-литерал помечается типом literal.
BLUEPRINTS: List[List[tuple[Any, str, Any]]] = [
    # 1. Причинная цепочка из трёх утверждений
    [("concept", "increases", "concept"),
     ("concept", "increases", "concept"),
     ("concept", "decreases", "concept")],
    # 2. Ветвление: один субъект — три разных объекта/предиката
    [("concept", "increases", "concept"),
     ("concept", "decreases", "concept"),
     ("concept", "inhibits", "concept")],
    # 3. Вложенное утверждение (внутреннее в объекте внешнего)
    [("concept", "upregulates", "concept"),          # s0
     ("concept", "explains", 0),                     # s1: объект = s0
     ("concept", "contradicts", 0)],                 # s2: субъект = s0
    # 4. Ветка с литералом
    [("concept", "correlates", "concept"),
     ("concept", "has_value", "literal"),
     ("concept", "downregulates", "concept")],
    # 5. Двойное вложение (дерево глубины 3)
    [("concept", "increases", "concept"),            # s0
     ("concept", "suppresses", "concept"),           # s1
     (0, "contradicts", "concept"),                  # s2: субъект = s0
     (2, "supports", 0)],                            # s3: субъект = s2, объект = s0
    # 6. Глубокая цепочка из пяти утверждений
    [("concept", "promotes", "concept"),
     ("concept", "increases", "concept"),
     ("concept", "inhibits", "concept"),
     ("concept", "correlates", "concept"),
     ("concept", "has_value", "literal")],
    # 7. Звезда с вложением
    [("concept", "activates", "concept"),            # s0
     (0, "requires", "concept"),                     # s1: объект = s0 (вложен.)
     ("concept", "blocks", 0),                       # s2: субъект = s0
     ("concept", "induces", "concept")],
]

BLUE_NAMES = ["chain", "branch", "nested", "literal", "deep-nest", "chain5", "star-nest"]


def build_document(doc_uid: str, rng: random.Random) -> List[Dict[str, Any]]:
    """Строит утверждения одного синтетического документа.

    Возвращает список полей утверждений (uid, subject_text, predicate,
    object_text, subject_type, object_type, type, confidence, sort_order).
    Тексты концептов рандомизированы; для вложенных утверждений
    subject_text/object_text = uid внутреннего утверждения.
    """
    # 2–3 независимых шаблона на документ
    picked = rng.sample(range(len(BLUEPRINTS)), k=rng.randint(2, 3))
    rows: List[Dict[str, Any]] = []
    uid_by_slot: Dict[int, str] = {}
    order = 0
    text_of_slot: Dict[int, str] = {}

    for bp_idx in picked:
        blueprint = BLUEPRINTS[bp_idx]
        slots = [None] * len(blueprint)
        # сначала назначаем uid всем слотам, чтобы можно было строить ссылки
        for i in range(len(blueprint)):
            uid = uuid8_str()
            uid_by_slot[i] = uid
            slots[i] = uid
        for i, (skind, pred, okind) in enumerate(blueprint):
            sid = uid_by_slot[i]
            subj_text, stype = _text_for(skind, slots, text_of_slot, rng)
            obj_text, otype = _text_for(okind, slots, text_of_slot, rng)
            rows.append({
                "uid": sid,
                "subject_text": subj_text,
                "predicate": pred,
                "object_text": obj_text,
                "subject_type": stype,
                "object_type": otype,
                "type": "FACT",
                "confidence": round(rng.uniform(0.8, 1.0), 3),
                "sort_order": order,
            })
            text_of_slot[i] = f"{subj_text} {pred} {obj_text}"
            order += 1

    for r in rows:
        r.setdefault("created_by_uid", "synth-pattern-miner")
    return rows


def _text_for(kind: Any, slots: List[str], text_of_slot: Dict[int, str], rng: random.Random):
    if kind == "concept":
        return norm_concept(rng.choice([CONCEPT_POOL_A, CONCEPT_POOL_B]), rng), "concept"
    if kind == "literal":
        return rng.choice(LITERAL_POOL), "literal"
    # kind — индекс слота: вложенное утверждение
    return text_of_slot.get(kind, slots[kind]), "statement"


def create_corpus(num_docs: int, rng: random.Random) -> None:
    print(f"Создаю {num_docs} синтетических документов…")
    for i in range(num_docs):
        doc_uid = f"synth-pm-{i:05d}"
        title = f"[SYNTH] km-pattern-test-{i:05d}"
        rows = build_document(doc_uid, rng)
        db.cypher_query(
            "MERGE (d:Document {uid: $doc_uid}) "
            "SET d.original_filename = $title, d.md5_hash = $doc_uid, d.s3_key = '', "
            "d.title = $title, d.processing_status = 'ready_for_annotation', "
            "d.is_processed = true, d.created_by_uid = 'synth-pattern-miner', d.synthetic = true",
            {"doc_uid": doc_uid, "title": title},
        )
        # разбиение на батчи
        for chunk_start in range(0, len(rows), 500):
            chunk = rows[chunk_start:chunk_start + 500]
            db.cypher_query(
                "MATCH (d:Document {uid: $doc_uid}) "
                "UNWIND $batch AS item "
                "CREATE (s:KnowledgeStatement {uid: item.uid, subject_text: item.subject_text, "
                "predicate: item.predicate, object_text: item.object_text, "
                "subject_type: item.subject_type, object_type: item.object_type, "
                "type: item.type, confidence: item.confidence, sentence_text: '', "
                "sort_order: item.sort_order, created_by_uid: item.created_by_uid}) "
                "CREATE (d)-[:HAS_STATEMENT]->(s)",
                {"doc_uid": doc_uid, "batch": chunk},
            )
        if i % 50 == 0:
            print(f"  …{i}")
    print("Готово.")


def clear_corpus() -> None:
    rows, _ = db.cypher_query(
        "MATCH (d:Document {synthetic: true}) "
        "OPTIONAL MATCH (d)-[r:HAS_STATEMENT]->(s:KnowledgeStatement) DELETE r, s, d "
        "RETURN count(DISTINCT d) AS n",
    )
    print(f"Удалено синтетических документов: {rows[0][0] if rows else 0}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Синтетический корпус для pattern-miner")
    parser.add_argument("--docs", type=int, default=200, help="Число структурных документов")
    parser.add_argument("--semantic-docs", type=int, default=0,
                        help="Число семантических документов (для генерации знания)")
    parser.add_argument("--seed", type=int, default=42, help="Сид генерации")
    parser.add_argument("--clear", action="store_true", help="Удалить синтетический корпус")
    args = parser.parse_args()

    if args.clear:
        clear_corpus()
        return

    rng = random.Random(args.seed)
    # Чистим старый синтетический корпус (idempotent)
    clear_corpus()
    if args.docs:
        create_corpus(args.docs, rng)
    if args.semantic_docs:
        create_semantic_corpus(args.semantic_docs, rng)


if __name__ == "__main__":
    sys.exit(main())
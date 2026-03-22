"""
Layer: Interface Adapters — Repository
Package: adapters.repositories.linguistic_pattern_repository
Responsibility: neomodel/Cypher-реализация LinguisticPatternRepositoryProtocol.

Allowed imports: neomodel, infrastructure.neo4j.orm_models, domain.exceptions
Forbidden imports: fastapi, web
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from neomodel import db

logger = logging.getLogger(__name__)


class LinguisticPatternRepository:
    """
    Cypher-реализация репозитория лингвистических паттернов.
    Удовлетворяет LinguisticPatternRepositoryProtocol (structural subtyping).
    """

    # ------------------------------------------------------------------
    # save_patterns
    # ------------------------------------------------------------------

    def save_patterns(self, patterns: List[Dict[str, Any]], doc_id: str) -> int:
        """
        Пакетно сохраняет лингвистические паттерны в Neo4j.
        Для каждого паттерна создаёт/обновляет узел LinguisticPattern и
        связывает его с MarkdownAnnotation через FOUND_IN.
        Для паттернов типа head_dep_chain дополнительно создаёт LexicalForm-узлы
        и DEP_RELATION-рёбра.
        Возвращает количество обработанных паттернов.
        """
        if not patterns:
            return 0

        # Назначить uid тем паттернам, у которых его нет
        rows = []
        for p in patterns:
            row = dict(p)
            row.setdefault("uid", str(uuid.uuid4()))
            rows.append(row)

        # --- Создаём/обновляем LinguisticPattern + FOUND_IN ---
        cypher_pattern = """
UNWIND $rows AS row
MERGE (lp:LinguisticPattern {
    pattern_str: row.pattern_str,
    pattern_type: row.pattern_type,
    annotation_type: row.annotation_type,
    doc_id: row.doc_id
})
ON CREATE SET
    lp.uid = row.uid,
    lp.frequency = row.frequency
ON MATCH SET
    lp.frequency = lp.frequency + row.frequency
WITH lp, row
MATCH (ann:MarkdownAnnotation {uid: row.annotation_uid})
MERGE (lp)-[:FOUND_IN]->(ann)
RETURN count(lp) AS cnt
"""
        result, _ = db.cypher_query(cypher_pattern, {"rows": rows})
        saved = result[0][0] if result else 0

        # --- Для head_dep_chain создаём LexicalForm + DEP_RELATION ---
        chain_rows = [r for r in rows if r.get("pattern_type") == "head_dep_chain"]
        if chain_rows:
            lf_rows = _parse_chain_rows(chain_rows)
            if lf_rows:
                _save_lexical_forms(lf_rows)

        return saved

    # ------------------------------------------------------------------
    # get_for_document
    # ------------------------------------------------------------------

    def get_for_document(
        self,
        doc_id: str,
        annotation_types: Optional[List[str]] = None,
        min_frequency: int = 1,
    ) -> List[Dict[str, Any]]:
        """Возвращает паттерны документа, опционально фильтруя по типу аннотации."""
        cypher = """
MATCH (lp:LinguisticPattern {doc_id: $doc_id})
WHERE lp.frequency >= $min_frequency
  AND ($types IS NULL OR lp.annotation_type IN $types)
RETURN lp.pattern_str   AS pattern_str,
       lp.pattern_type  AS pattern_type,
       lp.annotation_type AS annotation_type,
       lp.frequency     AS frequency
ORDER BY lp.annotation_type, lp.frequency DESC
"""
        result, cols = db.cypher_query(cypher, {
            "doc_id": doc_id,
            "min_frequency": min_frequency,
            "types": annotation_types,
        })
        return [dict(zip(cols, row)) for row in result]

    # ------------------------------------------------------------------
    # delete_for_document
    # ------------------------------------------------------------------

    def delete_for_document(self, doc_id: str) -> int:
        """Удаляет все паттерны и связанные LexicalForm-узлы документа."""
        cypher = """
MATCH (lp:LinguisticPattern {doc_id: $doc_id})
WITH lp
OPTIONAL MATCH (lf:LexicalForm {doc_id: $doc_id})
WITH lp, collect(lf) AS lfs
FOREACH (lf IN lfs | DETACH DELETE lf)
WITH lp
DETACH DELETE lp
RETURN count(lp)
"""
        result, _ = db.cypher_query(cypher, {"doc_id": doc_id})
        return result[0][0] if result else 0


# ---------------------------------------------------------------------------
# Вспомогательные функции для head_dep_chain
# ---------------------------------------------------------------------------

def _parse_chain_rows(chain_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Разбирает строки паттернов head_dep_chain вида:
        "head/POS →[rel]→ dep/POS"
    и формирует структуры для создания LexicalForm-узлов.
    """
    lf_rows = []
    for row in chain_rows:
        pattern_str: str = row.get("pattern_str", "")
        try:
            # "head/POS →[rel]→ dep/POS"
            left, right = pattern_str.split(" →[")
            rel_part, dep_part = right.split("]→ ")
            head_text, head_pos = left.rsplit("/", 1)
            dep_text, dep_pos = dep_part.strip().rsplit("/", 1)
        except (ValueError, AttributeError):
            continue

        lf_rows.append({
            "head_text": head_text.strip(),
            "head_pos": head_pos.strip(),
            "dep_text": dep_text.strip(),
            "dep_pos": dep_pos.strip(),
            "relation": rel_part.strip(),
            "doc_id": row["doc_id"],
            "annotation_uid": row["annotation_uid"],
            "pattern_uid": row["uid"],
        })
    return lf_rows


def _save_lexical_forms(lf_rows: List[Dict[str, Any]]) -> None:
    """Создаёт LexicalForm-узлы и DEP_RELATION-рёбра пакетным Cypher-запросом."""
    cypher = """
UNWIND $rows AS row
MERGE (h:LexicalForm {text: row.head_text, pos: row.head_pos, doc_id: row.doc_id})
  ON CREATE SET h.uid = randomUUID(),
                h.annotation_uid = row.annotation_uid
MERGE (d:LexicalForm {text: row.dep_text, pos: row.dep_pos, doc_id: row.doc_id})
  ON CREATE SET d.uid = randomUUID(),
                d.annotation_uid = row.annotation_uid
MERGE (d)-[r:DEP_RELATION {
    relation_type: row.relation,
    doc_id: row.doc_id,
    annotation_uid: row.annotation_uid
}]->(h)
WITH h, d, row
MATCH (lp:LinguisticPattern {uid: row.pattern_uid})
MERGE (h)-[:PART_OF]->(lp)
MERGE (d)-[:PART_OF]->(lp)
"""
    try:
        db.cypher_query(cypher, {"rows": lf_rows})
    except Exception as e:
        logger.warning(f"[linguistic_patterns] Ошибка создания LexicalForm-узлов: {e}")

"""
Скрипт для создания индексов и constraints в Neo4j для Action и LexicalUnit.

Запуск: poetry run python scripts/create_linguistic_indexes.py
"""
import os
import logging
from neo4j import GraphDatabase

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

INDEXES = [
    # ── Constraints (unique) ──
    "CREATE CONSTRAINT action_uid_unique IF NOT EXISTS FOR (n:Action) REQUIRE n.uid IS UNIQUE",
    "CREATE CONSTRAINT lexical_uid_unique IF NOT EXISTS FOR (n:LexicalUnit) REQUIRE n.uid IS UNIQUE",

    # ── Composite / property indexes ──
    "CREATE INDEX action_doc_id IF NOT EXISTS FOR (n:Action) ON (n.doc_id)",
    "CREATE INDEX action_verb IF NOT EXISTS FOR (n:Action) ON (n.verb)",
    "CREATE INDEX action_class IF NOT EXISTS FOR (n:Action) ON (n.action_class)",
    "CREATE INDEX action_norm_key IF NOT EXISTS FOR (n:Action) ON (n.norm_key)",

    "CREATE INDEX lexical_doc_id IF NOT EXISTS FOR (n:LexicalUnit) ON (n.doc_id)",
    "CREATE INDEX lexical_pos IF NOT EXISTS FOR (n:LexicalUnit) ON (n.pos)",
    "CREATE INDEX lexical_lemma IF NOT EXISTS FOR (n:LexicalUnit) ON (n.lemma)",
    "CREATE INDEX lexical_dep IF NOT EXISTS FOR (n:LexicalUnit) ON (n.dep)",
]


def main():
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as session:
            for query in INDEXES:
                name = query.split("IF NOT EXISTS")[0].replace("CREATE ", "").strip()
                try:
                    session.run(query)
                    logger.info(f"OK: {name}")
                except Exception as e:
                    logger.warning(f"SKIP: {name} — {e}")

        logger.info("Все индексы созданы (или уже существуют).")
    finally:
        driver.close()


if __name__ == "__main__":
    main()

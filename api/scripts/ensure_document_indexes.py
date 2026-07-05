"""
Скрипт для создания индексов Neo4j на узлах Document.
Запускать: poetry run python scripts/ensure_document_indexes.py
"""
import logging
from neomodel import db

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

INDEXES = [
    "CREATE INDEX IF NOT EXISTS FOR (d:Document) ON (d.upload_date)",
    "CREATE INDEX IF NOT EXISTS FOR (d:Document) ON (d.processing_status)",
    "CREATE INDEX IF NOT EXISTS FOR (d:Document) ON (d.source)",
]

TEXT_INDEXES = [
    "CREATE TEXT INDEX IF NOT EXISTS FOR (d:Document) ON (d.title)",
    "CREATE TEXT INDEX IF NOT EXISTS FOR (d:Document) ON (d.original_filename)",
]

if __name__ == "__main__":
    from neomodel import config as neomodel_config
    from infrastructure.config import settings
    neomodel_config.DATABASE_URL = settings.get_database_url()
    if not settings.NEO4J_URI.startswith(("bolt+s://", "neo4j+s://")):
        neomodel_config.ENCRYPTED = False

    for cypher in INDEXES + TEXT_INDEXES:
        try:
            db.cypher_query(cypher)
            logger.info(f"OK: {cypher}")
        except Exception as e:
            logger.error(f"FAIL: {cypher}: {e}")

    logger.info("Индексы созданы.")

"""Inspect Neo4j Document records for the article-pipeline gold corpus."""
from __future__ import annotations

import sys
from pathlib import Path

from neo4j import GraphDatabase

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))

from infrastructure.config import settings


PMCID_LIST = [
    "PMC10000452", "PMC10000584", "PMC10000897", "PMC10000969", "PMC10001272",
    "PMC10001331", "PMC10001353", "PMC10001413", "PMC10001821", "PMC10001833",
    "PMC10001974", "PMC10002395", "PMC10002471", "PMC10002495", "PMC10002543",
    "PMC10002641", "PMC10002668", "PMC10002830", "PMC10002864", "PMC10002910",
]


def main() -> None:
    driver = GraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
    )
    try:
        users = driver.execute_query(
            "MATCH (u:User) RETURN u.uid AS uid, u.login AS login, u.nickname AS nickname "
            "ORDER BY u.uid LIMIT 20",
            database_="neo4j",
        ).records
        print("users:")
        for user in users:
            print(user.data())
        records = driver.execute_query(
            "MATCH (d:Document) WHERE d.pmc_id IN $ids "
            "OPTIONAL MATCH (d)-[:HAS_BLOCK]->(b:ArticleBlock) "
            "WITH d, count(b) AS blocks "
            "OPTIONAL MATCH (d)-[:HAS_STATEMENT]->(s:KnowledgeStatement) "
            "RETURN d.pmc_id AS pmc, d.uid AS uid, d.title AS title, "
            "d.source AS source, d.processing_status AS status, d.created_by_uid AS owner, "
            "d.current_source_hash AS source_hash, d.active_pipeline_version AS active_version, "
            "d.has_full_text AS full, d.user_md_s3_key AS userkey, "
            "d.formatted_md_s3_key AS fmt, d.docling_raw_md_s3_key AS raw, "
            "blocks, count(s) AS statements ORDER BY d.pmc_id",
            ids=PMCID_LIST,
            database_="neo4j",
        ).records
        print(f"count={len(records)}")
        for record in records:
            print(record.data())
    finally:
        driver.close()


if __name__ == "__main__":
    main()

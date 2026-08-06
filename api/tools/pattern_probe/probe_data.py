"""Temporary probe: survey Neo4j data for the outcome-pattern prototype."""
import json
import sys
from collections import Counter

from neomodel import db
from neomodel import config as neomodel_config

neomodel_config.DATABASE_URL = "bolt://neo4j:password@127.0.0.1:7687"
neomodel_config.ENCRYPTED = False

TARGET = "000657ba-aec6-8a11-9c5c-986526539651"


def q(cypher, **params):
    res, _ = db.cypher_query(cypher, params)
    return res


def main():
    docs = q(
        "MATCH (d:Document) RETURN d.uid, d.title, d.processing_status "
        "ORDER BY d.upload_date DESC LIMIT 30"
    )
    print("=== DOCUMENTS (latest 30) ===")
    for uid, title, status in docs:
        mark = " <== TARGET" if uid == TARGET else ""
        print(f"{uid} | {title!r} | {status}{mark}")

    print("\n=== TARGET DOC ===")
    for row in q(
        "MATCH (d:Document {uid:$u}) RETURN d.uid, d.title, d.processing_status, d.doi",
        u=TARGET,
    ):
        print(row)

    print("\n=== TARGET STATEMENTS / BLOCKS ===")
    st_count = q(
        "MATCH (d:Document {uid:$u})-[:HAS_STATEMENT]->(s:KnowledgeStatement) RETURN count(s)",
        u=TARGET,
    )[0][0]
    bl_count = q(
        "MATCH (d:Document {uid:$u})-[:HAS_BLOCK]->(b:ArticleBlock) RETURN count(b)",
        u=TARGET,
    )[0][0]
    print(f"statements={st_count} blocks={bl_count}")

    print("\n=== BLOCK TYPE DISTRIBUTION (target) ===")
    for bt, cnt in q(
        "MATCH (d:Document {uid:$u})-[:HAS_BLOCK]->(b:ArticleBlock) "
        "RETURN b.block_type, count(*) ORDER BY count(*) DESC",
        u=TARGET,
    ):
        print(f"T{bt}: {cnt}")

    print("\n=== META PREDICATE DISTRIBUTION (target) ===")
    for pred, cnt in q(
        "MATCH (d:Document {uid:$u})-[:HAS_STATEMENT]->(s:KnowledgeStatement {type:'META'}) "
        "RETURN s.predicate, count(*) ORDER BY count(*) DESC",
        u=TARGET,
    ):
        print(f"{pred}: {cnt}")

    print("\n=== FACT PREDICATE DISTRIBUTION (target, top 40) ===")
    for pred, cnt in q(
        "MATCH (d:Document {uid:$u})-[:HAS_STATEMENT]->(s:KnowledgeStatement {type:'FACT'}) "
        "RETURN s.predicate, count(*) ORDER BY count(*) DESC LIMIT 40",
        u=TARGET,
    ):
        print(f"{pred}: {cnt}")


if __name__ == "__main__":
    main()

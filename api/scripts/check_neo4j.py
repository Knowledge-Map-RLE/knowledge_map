"""Check document status in Neo4j."""
from neomodel import db

db.set_connection("bolt://neo4j:password@127.0.0.1:7687")
results, _ = db.cypher_query(
    "MATCH (d:Document) WHERE d.uid = $uid RETURN d.uid, d.processing_status, d.is_processed, d.docling_raw_md_s3_key, d.formatted_md_s3_key, d.user_md_s3_key, d.has_markdown",
    {"uid": "886f1448799d4aba1076c65e059a3d58"},
)
for row in results:
    print(f"uid: {row[0]}")
    print(f"processing_status: {row[1]}")
    print(f"is_processed: {row[2]}")
    print(f"docling_raw_md_s3_key: {row[3]}")
    print(f"formatted_md_s3_key: {row[4]}")
    print(f"user_md_s3_key: {row[5]}")
    print(f"has_markdown: {row[6]}")

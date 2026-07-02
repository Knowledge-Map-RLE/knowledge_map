"""Check document status after reconversion."""
from neomodel import config
config.DATABASE_URL = "bolt://neo4j:password@127.0.0.1:7687"
config.ENCRYPTED = False
from neomodel import db

r, _ = db.cypher_query(
    "MATCH (d:Document) WHERE d.uid = '886f1448799d4aba1076c65e059a3d58' RETURN d.uid, d.processing_status, d.is_processed, d.docling_raw_md_s3_key, d.formatted_md_s3_key",
)
print("Document status:", r)

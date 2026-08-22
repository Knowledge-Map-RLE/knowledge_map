from neo4j import GraphDatabase
import time

d = GraphDatabase.driver("bolt://127.0.0.1:7687", auth=("neo4j", "password"))
s = d.session()

t0 = time.monotonic()
r = s.run(
    "MATCH (d:Document) WHERE d.docling_raw_md_s3_key IS NOT NULL "
    "SET d.has_full_text = true "
    "RETURN count(d) AS updated"
)
updated = r.single()["updated"]
print(f"Backfilled has_full_text=true for {updated} documents in {time.monotonic()-t0:.1f}s")

d.close()

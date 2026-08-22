import time
from neo4j import GraphDatabase

d = GraphDatabase.driver("bolt://127.0.0.1:7687", auth=("neo4j", "password"))
s = d.session()

# Test has_full_text index
t0 = time.monotonic()
r = s.run("MATCH (d:Document) WHERE d.has_full_text = true RETURN count(d) as c")
print(f"count via has_full_text index: {r.single()['c']} in {time.monotonic()-t0:.3f}s")

t0 = time.monotonic()
r = s.run("MATCH (d:Document) WHERE d.has_full_text = true RETURN d.uid, d.title ORDER BY d.uid SKIP 0 LIMIT 10")
rows = r.data()
print(f"list via has_full_text: {len(rows)} rows in {time.monotonic()-t0:.3f}s")

# Compare with old approach
t0 = time.monotonic()
r = s.run("MATCH (d:Document) WHERE d.docling_raw_md_s3_key IS NOT NULL RETURN count(d) as c")
print(f"count via IS NOT NULL: {r.single()['c']} in {time.monotonic()-t0:.3f}s")

d.close()

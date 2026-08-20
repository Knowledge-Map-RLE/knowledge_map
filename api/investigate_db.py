"""Check PubMed Baseline download status."""
from neo4j import GraphDatabase
import time

d = GraphDatabase.driver("bolt://127.0.0.1:7687", auth=("neo4j", "password"))
s = d.session()

# DataSource nodes
print("=== DataSource nodes ===")
r = s.run("MATCH (n:DataSource) RETURN n LIMIT 10")
for rec in r:
    n = rec["n"]
    d2 = dict(n)
    for k, v in d2.items():
        if isinstance(v, str) and len(v) > 100:
            d2[k] = v[:100] + "..."
    print(d2)

# Document count by source
print("\n=== Document count by source ===")
r = s.run("""
    MATCH (d:Document)
    RETURN d.source as source, count(d) as cnt
    ORDER BY cnt DESC
""")
for rec in r:
    print("  %s: %d" % (rec["source"], rec["cnt"]))

# Check pubmed_id distribution
print("\n=== PubMed Document pubmed_id stats ===")
r = s.run("""
    MATCH (d:Document) WHERE d.source = 'pubmed'
    RETURN count(d) as total,
           count(d.pubmed_id) as with_pmid,
           count(d.title) as with_title,
           count(d.abstract) as with_abstract
""")
for rec in r:
    print(dict(rec))

# Check pmc documents
print("\n=== PMC Documents ===")
r = s.run("""
    MATCH (d:Document) WHERE d.source = 'pmc'
    RETURN count(d) as total,
           count(d.pmc_id) as with_pmcid,
           count(d.pubmed_id) as with_pmid
""")
for rec in r:
    print(dict(rec))

# Article count
r = s.run("MATCH (a:Article) RETURN count(a) as cnt")
print("\n=== Article count: %d ===" % r.single()["cnt"])

# BIBLIOGRAPHIC_LINK count
r = s.run("MATCH ()-[r:BIBLIOGRAPHIC_LINK]->() RETURN count(r) as cnt")
print("BIBLIOGRAPHIC_LINK count: %d" % r.single()["cnt"])

d.close()

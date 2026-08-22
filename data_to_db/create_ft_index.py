from neo4j import GraphDatabase

d = GraphDatabase.driver("bolt://127.0.0.1:7687", auth=("neo4j", "password"))
s = d.session()

r = s.run("CREATE INDEX idx_doc_has_full_text IF NOT EXISTS FOR (d:Document) ON (d.has_full_text)")
summary = r.consume()
print(f"Index created: {summary.counters}")

d.close()

from neo4j import GraphDatabase

d = GraphDatabase.driver("bolt://127.0.0.1:7687", auth=("neo4j", "password"))
s = d.session()

r = s.run("MATCH (n:Document) WHERE n.source='pmc' AND n.docling_raw_md_s3_key IS NOT NULL RETURN count(n) as c")
print("PMC with full text:", r.single()["c"])

r = s.run("MATCH (n:Document) WHERE n.source='pmc' RETURN count(n) as c")
print("PMC total:", r.single()["c"])

r = s.run("MATCH (n:Document) WHERE n.source='pmc' AND n.docling_raw_md_s3_key IS NULL RETURN count(n) as c")
print("PMC without full text:", r.single()["c"])

d.close()

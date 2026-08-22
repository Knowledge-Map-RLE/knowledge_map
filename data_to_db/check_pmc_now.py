import sys, os
sys.path.insert(0, r"D:\Knowledge_Map\data_to_db")
from common import get_driver

driver = get_driver()
with driver.session() as s:
    r = s.run("MATCH (d:Document) WHERE d.source = 'pmc' RETURN count(d) as cnt")
    print(f"PMC in Neo4j: {r.single()['cnt']}")
    r2 = s.run("MATCH (d:Document) WHERE d.source = 'pmc' AND d.docling_raw_md_s3_key IS NOT NULL RETURN count(d) as cnt")
    print(f"PMC with full text: {r2.single()['cnt']}")
    r3 = s.run("MATCH (d:Document) WHERE d.source = 'pmc' AND d.processing_status = 'processed' RETURN count(d) as cnt")
    print(f"PMC processed: {r3.single()['cnt']}")
driver.close()

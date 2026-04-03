import sys
sys.path.insert(0, "d:/Knowledge_Map/api")
from neomodel import config, db
config.DATABASE_URL = "bolt://neo4j:password@127.0.0.1:7687"

# Check indexes
r, _ = db.cypher_query("SHOW INDEXES YIELD name, type, labelsOrTypes, properties WHERE 'Action' IN labelsOrTypes RETURN name, type, properties")
LOG = open("d:/Knowledge_Map/eval/check_index_out.txt", "w")
LOG.write("Action indexes:\n")
for row in r:
    LOG.write(f"  {row}\n")
    print(row)

# Also try update with BATCH=500
LOG.write("\nTesting small batch update...\n")
# Get 500 edges
edges, _ = db.cypher_query("""
    MATCH (s:Action)-[rel:LEADS_TO]->(t:Action)
    WHERE rel.relation_subtype <> 'PART_OF_GOAL'
    AND rel.status = 'pending'
    RETURN s.uid, t.uid, rel.relation_subtype
    LIMIT 500
""")
LOG.write(f"Got {len(edges)} sample edges\n")

import time
t = time.time()
if edges:
    pairs = [{'src': r[0], 'tgt': r[1], 'rel': r[2]} for r in edges[:100]]
    db.cypher_query("""
        UNWIND $pairs AS p
        MATCH (s:Action {uid: p.src})-[rel:LEADS_TO {relation_subtype: p.rel}]->(t:Action {uid: p.tgt})
        SET rel.status = 'rejected'
    """, {'pairs': pairs})
    LOG.write(f"Updated 100 edges in {time.time()-t:.2f}s\n")
    print(f"100 edge update: {time.time()-t:.2f}s")
LOG.close()

"""Bulk-update LEADS_TO statuses using uid-based node lookup (fastest with index)."""
import sys, time
sys.path.insert(0, "d:/Knowledge_Map/api")

from neomodel import config, db
config.DATABASE_URL = "bolt://neo4j:password@127.0.0.1:7687"

from auto_review import should_confirm

LOG = open("d:/Knowledge_Map/eval/rerun_out.txt", "w", encoding="utf-8", buffering=1)

def out(msg):
    LOG.write(msg + "\n")
    LOG.flush()
    print(msg, flush=True)

t0 = time.time()

# Step 0: Create index on Action.uid if not exists
out("Step 0: Creating index on Action.uid...")
try:
    db.cypher_query("CREATE INDEX action_uid IF NOT EXISTS FOR (a:Action) ON (a.uid)")
    out("  Index created (or already exists).")
except Exception as e:
    out(f"  Index creation: {e}")

# Step 0b: Warmup — force Neo4j to cache the index
out("Step 0b: Warming up Action.uid index...")
db.cypher_query("MATCH (a:Action) WHERE a.uid IS NOT NULL RETURN count(a)")
out("  Warmup done.")
time.sleep(1)

# Step 1: Reset
out("Step 1: Resetting all LEADS_TO edges to pending...")
r, _ = db.cypher_query("""
    MATCH ()-[rel:LEADS_TO]->()
    WHERE rel.relation_subtype <> 'PART_OF_GOAL'
    AND rel.status IN ['confirmed', 'rejected']
    SET rel.status = 'pending'
    RETURN count(rel)
""")
out(f"  Reset {r[0][0]} edges. ({time.time()-t0:.1f}s)")

# Step 2: Load all pending edges
out("Step 2: Loading all pending edges...")
t1 = time.time()
edges, _ = db.cypher_query("""
    MATCH (s:Action)-[rel:LEADS_TO]->(t:Action)
    WHERE rel.relation_subtype <> 'PART_OF_GOAL'
    AND rel.status = 'pending'
    RETURN s.uid, t.uid, s.full_phrase, t.full_phrase,
           rel.relation_subtype, rel.confidence, rel.evidence
""")
out(f"  Loaded {len(edges)} edges. ({time.time()-t1:.1f}s)")

# Step 3: Classify
out("Step 3: Classifying edges...")
t2 = time.time()
to_confirm = []
to_reject = []

for src_uid, tgt_uid, src_phrase, tgt_phrase, relation, confidence, evidence in edges:
    confidence = float(confidence) if confidence is not None else 0.0
    evidence = list(evidence) if evidence else []
    ok, _ = should_confirm(src_phrase, tgt_phrase, relation, confidence, evidence)
    entry = {'src': src_uid, 'tgt': tgt_uid, 'rel': relation}
    if ok:
        to_confirm.append(entry)
    else:
        to_reject.append(entry)

total = len(to_confirm) + len(to_reject)
rate = len(to_confirm) / total * 100 if total > 0 else 0
out(f"  to_confirm={len(to_confirm)} ({rate:.1f}%)  to_reject={len(to_reject)}  ({time.time()-t2:.1f}s)")

# Step 4: Test speed with 1000 batch (after warmup, should be fast)
out("Step 4: Testing update speed with 1000-edge batch...")
t_test = time.time()
test_chunk = to_reject[:1000]
db.cypher_query("""
    UNWIND $pairs AS p
    MATCH (s:Action {uid: p.src})-[rel:LEADS_TO {relation_subtype: p.rel}]->(t:Action {uid: p.tgt})
    SET rel.status = 'rejected'
""", {'pairs': test_chunk})
speed = 1000 / (time.time() - t_test)
out(f"  Speed: {speed:.0f} edges/s with index")

# If still slow, try a second warmup batch
if speed < 100:
    out("  Speed too slow — running second warmup batch...")
    t_test2 = time.time()
    test_chunk2 = to_reject[1000:2000]
    db.cypher_query("""
        UNWIND $pairs AS p
        MATCH (s:Action {uid: p.src})-[rel:LEADS_TO {relation_subtype: p.rel}]->(t:Action {uid: p.tgt})
        SET rel.status = 'rejected'
    """, {'pairs': test_chunk2})
    speed2 = 1000 / (time.time() - t_test2)
    out(f"  Speed after second warmup: {speed2:.0f} edges/s")
    speed = speed2
    skip_reject = 2000
else:
    skip_reject = 1000

# Step 5: Bulk update with optimal batch
BATCH = max(1000, min(10000, int(speed * 5)))
out(f"Step 5: Bulk updating with BATCH={BATCH}...")
t3 = time.time()

for status, pairs, skip in [
    ('rejected', to_reject, skip_reject),
    ('confirmed', to_confirm, 0),
]:
    for i in range(skip, len(pairs), BATCH):
        chunk = pairs[i:i+BATCH]
        db.cypher_query("""
            UNWIND $pairs AS p
            MATCH (s:Action {uid: p.src})-[rel:LEADS_TO {relation_subtype: p.rel}]->(t:Action {uid: p.tgt})
            SET rel.status = $status
        """, {'pairs': chunk, 'status': status})
    out(f"  {status}: {len(pairs)} total done. ({time.time()-t3:.1f}s)")

total_time = time.time() - t0
out(f"\nDone in {total_time:.1f}s")
out(f"  confirmed={len(to_confirm)} ({rate:.1f}%)")
out(f"  rejected={len(to_reject)}")
LOG.close()

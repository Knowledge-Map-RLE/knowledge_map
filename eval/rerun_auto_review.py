"""
Re-run auto_review for ALL done articles using updated should_confirm rules.

Steps:
1. Reset all LEADS_TO edges (excluding PART_OF_GOAL) to status='pending'
2. Re-run auto_review.run() for each document with actions

Run: cd d:\\Knowledge_Map\\api && poetry run python -W ignore -c "exec(open('d:/Knowledge_Map/eval/rerun_auto_review.py').read())"
"""
import sys
sys.path.insert(0, "d:/Knowledge_Map/api")

import os
os.environ.setdefault("NEO4J_URI", "bolt://neo4j:password@127.0.0.1:7687")

from neomodel import config, db
config.DATABASE_URL = "bolt://neo4j:password@127.0.0.1:7687"

from auto_review import run as ar_run

# 1. Reset all LEADS_TO edges to pending (except PART_OF_GOAL)
print("Step 1: Resetting all LEADS_TO edges to pending...", flush=True)
res, _ = db.cypher_query("""
    MATCH ()-[r:LEADS_TO]->()
    WHERE r.relation_subtype <> 'PART_OF_GOAL'
    AND (r.status = 'confirmed' OR r.status = 'rejected')
    SET r.status = 'pending'
    RETURN count(r) AS reset_count
""")
reset_count = res[0][0] if res else 0
print(f"  Reset {reset_count} edges to pending", flush=True)

# 2. Get all doc_ids that have Action nodes
print("\nStep 2: Loading doc_ids with Action nodes...", flush=True)
res2, _ = db.cypher_query("""
    MATCH (a:Action)
    RETURN DISTINCT a.doc_id AS doc_id
""")
doc_ids = [r[0] for r in res2 if r[0]]
print(f"  Found {len(doc_ids)} documents with actions", flush=True)

# 3. Re-run auto_review for each
print(f"\nStep 3: Re-running auto_review for {len(doc_ids)} documents...", flush=True)
total_confirmed = 0
total_rejected = 0

for i, doc_id in enumerate(doc_ids, 1):
    result = ar_run(doc_id, dry_run=False, quiet=True)
    total_confirmed += result.get("confirmed", 0)
    total_rejected += result.get("rejected", 0)
    if i % 50 == 0 or i == len(doc_ids):
        pct = i / len(doc_ids) * 100
        rate = total_confirmed / (total_confirmed + total_rejected) * 100 if (total_confirmed + total_rejected) > 0 else 0
        print(f"  [{i:4d}/{len(doc_ids)}] {pct:.0f}% done | confirmed={total_confirmed} rejected={total_rejected} rate={rate:.1f}%", flush=True)

total = total_confirmed + total_rejected
rate = total_confirmed / total * 100 if total > 0 else 0
print(f"\nDone!")
print(f"  Total confirmed: {total_confirmed} ({rate:.1f}%)")
print(f"  Total rejected:  {total_rejected} ({100-rate:.1f}%)")

with open("d:/Knowledge_Map/eval/rerun_out.txt", "w", encoding="utf-8") as f:
    f.write(f"reset={reset_count}\nconfirmed={total_confirmed}\nrejected={total_rejected}\nrate={rate:.1f}%\n")
print("Results saved to eval/rerun_out.txt", flush=True)

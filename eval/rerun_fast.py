"""
Fast re-run of auto_review for all documents.
Loads ALL edges into Python, applies should_confirm, bulk-updates Neo4j.

Doc-level bio check: for each doc_id, pre-computes whether >=30% of
its action phrases contain a bio-domain token. Edges from bio-docs
skip the per-phrase bio-domain check, so specialised biomedical
phrases ("DMPs", "CpG sites", "DML") are not incorrectly rejected.

Run: cd d:\\Knowledge_Map\\api && poetry run python -W ignore "d:/Knowledge_Map/eval/rerun_fast.py"
"""
import sys, time
from collections import defaultdict
sys.path.insert(0, "d:/Knowledge_Map/api")

from neomodel import config, db
config.DATABASE_URL = "bolt://neo4j:password@127.0.0.1:7687"

from auto_review import should_confirm, _has_bio_domain_token

LOG = open("d:/Knowledge_Map/eval/rerun_out.txt", "w", encoding="utf-8", buffering=1)

def out(msg):
    LOG.write(msg + "\n")
    LOG.flush()

t0 = time.time()

# Step 1: Reset all LEADS_TO (non-PART_OF_GOAL) to pending
out("Step 1: Resetting all LEADS_TO edges to pending...")
r, _ = db.cypher_query("""
    MATCH ()-[rel:LEADS_TO]->()
    WHERE rel.relation_subtype <> 'PART_OF_GOAL'
    AND rel.status IN ['confirmed', 'rejected']
    SET rel.status = 'pending'
    RETURN count(rel)
""")
out(f"  Reset {r[0][0]} edges. ({time.time()-t0:.1f}s)")

# Step 1b: Build doc-level bio cache
# A doc is "bio" if >=30% of its action phrases contain a bio-domain token.
out("Step 1b: Building doc-level bio cache...")
t1b = time.time()
phrases_rows, _ = db.cypher_query("""
    MATCH (a:Action)
    WHERE a.doc_id IS NOT NULL AND a.full_phrase IS NOT NULL
    RETURN a.doc_id, a.full_phrase
""")

doc_phrase_counts: dict[str, int] = defaultdict(int)
doc_bio_counts: dict[str, int] = defaultdict(int)
for doc_id, phrase in phrases_rows:
    doc_phrase_counts[doc_id] += 1
    if phrase and _has_bio_domain_token(phrase):
        doc_bio_counts[doc_id] += 1

BIO_DOC_THRESHOLD = 0.10  # >=10% phrases with bio token → doc is bio
bio_docs: set[str] = {
    doc_id
    for doc_id, total in doc_phrase_counts.items()
    if total > 0 and doc_bio_counts[doc_id] / total >= BIO_DOC_THRESHOLD
}
out(f"  Bio docs: {len(bio_docs)}/{len(doc_phrase_counts)} ({len(bio_docs)/len(doc_phrase_counts):.1%})  ({time.time()-t1b:.1f}s)")

# Step 2: Load ALL pending edges into Python at once
out("Step 2: Loading all pending edges...")
t1 = time.time()
edges, _ = db.cypher_query("""
    MATCH (s:Action)-[rel:LEADS_TO]->(t:Action)
    WHERE rel.relation_subtype <> 'PART_OF_GOAL'
    AND rel.status = 'pending'
    RETURN s.uid, t.uid, s.full_phrase, t.full_phrase,
           rel.relation_subtype, rel.confidence, rel.evidence, rel.doc_id
""")
out(f"  Loaded {len(edges)} edges. ({time.time()-t1:.1f}s)")

# Step 3: Apply should_confirm in Python (pure CPU, no DB)
out("Step 3: Classifying edges with should_confirm...")
t2 = time.time()
to_confirm = []
to_reject = []

for src_uid, tgt_uid, src_phrase, tgt_phrase, relation, confidence, evidence, doc_id in edges:
    confidence = float(confidence) if confidence is not None else 0.0
    evidence = list(evidence) if evidence else []
    doc_is_bio = (doc_id in bio_docs) if doc_id else False
    ok, _ = should_confirm(src_phrase, tgt_phrase, relation, confidence, evidence, doc_is_bio=doc_is_bio)
    entry = {'src': src_uid, 'tgt': tgt_uid, 'rel': relation}
    if ok:
        to_confirm.append(entry)
    else:
        to_reject.append(entry)

total = len(to_confirm) + len(to_reject)
rate = len(to_confirm) / total * 100 if total > 0 else 0
out(f"  to_confirm={len(to_confirm)} ({rate:.1f}%)  to_reject={len(to_reject)}  ({time.time()-t2:.1f}s)")

# Step 4: Bulk update in batches
BATCH = 10000
out(f"Step 4: Bulk updating Neo4j (batch={BATCH})...")
t3 = time.time()

for status, pairs in [('confirmed', to_confirm), ('rejected', to_reject)]:
    for i in range(0, len(pairs), BATCH):
        chunk = pairs[i:i+BATCH]
        db.cypher_query("""
            UNWIND $pairs AS p
            MATCH (s:Action {uid: p.src})-[rel:LEADS_TO {relation_subtype: p.rel}]->(t:Action {uid: p.tgt})
            SET rel.status = $status
        """, {'pairs': chunk, 'status': status})
    out(f"  {status}: {len(pairs)} updated ({time.time()-t3:.1f}s)")

total_time = time.time() - t0
out(f"\nDone in {total_time:.1f}s")
out(f"  confirmed={len(to_confirm)} ({rate:.1f}%)")
out(f"  rejected={len(to_reject)}")
LOG.close()

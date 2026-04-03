"""Diagnose articles with 0 Action nodes."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "api"))

from neomodel import config, db
config.DATABASE_URL = "bolt://neo4j:password@127.0.0.1:7687"

# Sample of empty articles from the report
EMPTY_PMCIDS = [
    "PMC13031993", "PMC13029399", "PMC13030317", "PMC13029186", "PMC13025163",
    "PMC13029052", "PMC13029236", "PMC13023869", "PMC13030045", "PMC13028534",
]

print("=== Diagnosing empty articles (0 Action nodes) ===\n")

status_counts = {}

for pmcid in EMPTY_PMCIDS:
    rows, _ = db.cypher_query(
        "MATCH (p:WorkerArticleProgress {pmcid: $pmcid}) RETURN p.doc_id, p.state, p.error_msg",
        {"pmcid": pmcid}
    )
    if not rows:
        print(f"{pmcid}: NOT FOUND in WorkerArticleProgress")
        continue

    doc_id, state, err = rows[0]
    print(f"{pmcid}: state={state}  doc_id={str(doc_id)[:16] if doc_id else 'None'}")

    if not doc_id:
        print(f"  -> no doc_id, err={err}")
        status_counts[f"no_doc_id/{state}"] = status_counts.get(f"no_doc_id/{state}", 0) + 1
        continue

    # Check PDFDocument
    res2, _ = db.cypher_query(
        """MATCH (d:PDFDocument {uid: $uid})
           RETURN d.processing_status, d.s3_key, d.docling_raw_md_s3_key,
                  d.formatted_md_s3_key, d.user_md_s3_key, d.title""",
        {"uid": doc_id}
    )
    if not res2:
        print(f"  -> PDFDocument NOT FOUND for doc_id={doc_id}")
        status_counts["no_pdf_doc"] = status_counts.get("no_pdf_doc", 0) + 1
        continue

    ps, sk, dk, fk, uk, title = res2[0]
    active_key = uk or fk or dk or sk
    print(f"  processing_status={ps}")
    print(f"  active_key={'PRESENT' if active_key else 'MISSING'}: {str(active_key)[:60] if active_key else None}")
    print(f"  title={str(title)[:80] if title else 'None'}")

    # Count actions
    ac, _ = db.cypher_query(
        "MATCH (a:Action {doc_id: $doc_id}) RETURN count(a)", {"doc_id": doc_id}
    )
    action_count = ac[0][0] if ac else 0
    print(f"  action_count={action_count}")

    key = f"ps={ps}/key={'Y' if active_key else 'N'}"
    status_counts[key] = status_counts.get(key, 0) + 1
    print()

print("\n=== Status breakdown ===")
for k, v in sorted(status_counts.items()):
    print(f"  {k}: {v}")

# Now broader stats: how many 'done' articles have 0 actions?
print("\n=== Broader stats: done articles vs action presence ===")
res3, _ = db.cypher_query("""
    MATCH (p:WorkerArticleProgress {state: 'done'})
    WHERE p.doc_id IS NOT NULL
    OPTIONAL MATCH (a:Action {doc_id: p.doc_id})
    WITH p.doc_id AS doc_id, count(a) AS action_count
    RETURN
        count(CASE WHEN action_count = 0 THEN 1 END) AS zero_action,
        count(CASE WHEN action_count > 0 THEN 1 END) AS has_action,
        count(*) AS total
""")
if res3:
    zero, has, total = res3[0]
    print(f"  total done: {total}")
    print(f"  with actions: {has} ({has/total*100:.1f}%)")
    print(f"  zero actions: {zero} ({zero/total*100:.1f}%)")

# Check what processing_status the zero-action docs have
print("\n=== Processing status of zero-action docs ===")
res4, _ = db.cypher_query("""
    MATCH (p:WorkerArticleProgress {state: 'done'})
    WHERE p.doc_id IS NOT NULL
    MATCH (d:PDFDocument {uid: p.doc_id})
    OPTIONAL MATCH (a:Action {doc_id: p.doc_id})
    WITH d.processing_status AS ps, count(a) AS actions
    WHERE actions = 0
    RETURN ps, count(*) AS cnt
    ORDER BY cnt DESC
""")
for ps, cnt in res4:
    print(f"  processing_status={ps}: {cnt} docs")

# Check if they have markdown keys
print("\n=== S3 key presence for zero-action docs ===")
res5, _ = db.cypher_query("""
    MATCH (p:WorkerArticleProgress {state: 'done'})
    WHERE p.doc_id IS NOT NULL
    MATCH (d:PDFDocument {uid: p.doc_id})
    OPTIONAL MATCH (a:Action {doc_id: p.doc_id})
    WITH d, count(a) AS actions
    WHERE actions = 0
    RETURN
        count(CASE WHEN d.user_md_s3_key IS NOT NULL THEN 1 END) AS has_user_key,
        count(CASE WHEN d.formatted_md_s3_key IS NOT NULL THEN 1 END) AS has_fmt_key,
        count(CASE WHEN d.docling_raw_md_s3_key IS NOT NULL THEN 1 END) AS has_raw_key,
        count(CASE WHEN d.s3_key IS NOT NULL THEN 1 END) AS has_s3_key,
        count(*) AS total
""")
if res5:
    hu, hf, hr, hs, tot = res5[0]
    print(f"  total zero-action docs: {tot}")
    print(f"  user_md_s3_key present: {hu}")
    print(f"  formatted_md present:   {hf}")
    print(f"  docling_raw present:    {hr}")
    print(f"  s3_key present:         {hs}")

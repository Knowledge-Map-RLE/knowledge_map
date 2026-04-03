"""Diagnose articles with 0 Action nodes - Windows safe version."""
import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

api_dir = "d:/Knowledge_Map/api"
sys.path.insert(0, api_dir)

from neomodel import config, db
config.DATABASE_URL = "bolt://neo4j:password@127.0.0.1:7687"

out = []

# 1. Broader stats: done articles with/without actions
res, _ = db.cypher_query("""
    MATCH (p:WorkerArticleProgress {state: 'done'})
    WHERE p.doc_id IS NOT NULL
    OPTIONAL MATCH (a:Action {doc_id: p.doc_id})
    WITH p.doc_id AS doc_id, count(a) AS action_count
    RETURN
        count(CASE WHEN action_count = 0 THEN 1 END) AS zero_action,
        count(CASE WHEN action_count > 0 THEN 1 END) AS has_action,
        count(*) AS total
""")
zero, has, total = res[0]
out.append(f"DONE articles total: {total}")
out.append(f"  with actions:  {has} ({has/total*100:.1f}%)")
out.append(f"  zero actions:  {zero} ({zero/total*100:.1f}%)")

# 2. processing_status of zero-action docs
res2, _ = db.cypher_query("""
    MATCH (p:WorkerArticleProgress {state: 'done'})
    WHERE p.doc_id IS NOT NULL
    MATCH (d:PDFDocument {uid: p.doc_id})
    OPTIONAL MATCH (a:Action {doc_id: p.doc_id})
    WITH d.processing_status AS ps, count(a) AS actions
    WHERE actions = 0
    RETURN ps, count(*) AS cnt
    ORDER BY cnt DESC
""")
out.append("\nprocessing_status of zero-action done docs:")
for ps, cnt in res2:
    out.append(f"  {ps}: {cnt}")

# 3. S3 key presence for zero-action docs
res3, _ = db.cypher_query("""
    MATCH (p:WorkerArticleProgress {state: 'done'})
    WHERE p.doc_id IS NOT NULL
    MATCH (d:PDFDocument {uid: p.doc_id})
    OPTIONAL MATCH (a:Action {doc_id: p.doc_id})
    WITH d, count(a) AS actions
    WHERE actions = 0
    RETURN
        count(CASE WHEN d.user_md_s3_key IS NOT NULL THEN 1 END) AS has_user,
        count(CASE WHEN d.formatted_md_s3_key IS NOT NULL THEN 1 END) AS has_fmt,
        count(CASE WHEN d.docling_raw_md_s3_key IS NOT NULL THEN 1 END) AS has_raw,
        count(CASE WHEN d.s3_key IS NOT NULL THEN 1 END) AS has_s3,
        count(*) AS tot
""")
hu, hf, hr, hs, tot = res3[0]
out.append(f"\nS3 keys for zero-action docs (total={tot}):")
out.append(f"  user_md:     {hu}")
out.append(f"  formatted:   {hf}")
out.append(f"  docling_raw: {hr}")
out.append(f"  s3_key:      {hs}")

# 4. Sample one zero-action doc to see its markdown key and title
res4, _ = db.cypher_query("""
    MATCH (p:WorkerArticleProgress {state: 'done'})
    WHERE p.doc_id IS NOT NULL
    MATCH (d:PDFDocument {uid: p.doc_id})
    OPTIONAL MATCH (a:Action {doc_id: p.doc_id})
    WITH p.pmcid AS pmcid, d, count(a) AS actions
    WHERE actions = 0
    RETURN pmcid, d.processing_status, d.s3_key, d.docling_raw_md_s3_key,
           d.formatted_md_s3_key, d.user_md_s3_key, d.title
    LIMIT 5
""")
out.append("\nSample zero-action docs:")
for row in res4:
    pmcid, ps, sk, dk, fk, uk, title = row
    active = uk or fk or dk or sk
    out.append(f"  {pmcid}: ps={ps} key={'Y:'+str(active)[:40] if active else 'MISSING'}")
    out.append(f"    title={str(title)[:70] if title else 'None'}")

# 5. Check if WorkerArticleProgress.state='done' but NO PDFDocument
res5, _ = db.cypher_query("""
    MATCH (p:WorkerArticleProgress {state: 'done'})
    WHERE p.doc_id IS NOT NULL
    OPTIONAL MATCH (d:PDFDocument {uid: p.doc_id})
    WITH p, d WHERE d IS NULL
    RETURN count(p) AS missing_pdf_doc
""")
out.append(f"\ndone articles with no PDFDocument: {res5[0][0]}")

# 6. Check LEADS_TO edge counts for articles with actions
res6, _ = db.cypher_query("""
    MATCH (p:WorkerArticleProgress {state: 'done'})
    WHERE p.doc_id IS NOT NULL
    OPTIONAL MATCH (a:Action {doc_id: p.doc_id})
    WITH p.doc_id AS doc_id, count(a) AS actions
    WHERE actions > 0
    OPTIONAL MATCH (s:Action {doc_id: doc_id})-[r:LEADS_TO]->(t:Action)
    RETURN
        count(CASE WHEN r.status='confirmed' THEN 1 END) AS confirmed,
        count(CASE WHEN r.status='rejected' THEN 1 END) AS rejected,
        count(CASE WHEN r.status='pending' THEN 1 END) AS pending,
        count(*) AS total_edges,
        count(DISTINCT doc_id) AS n_docs
    LIMIT 1
""")
if res6:
    c, rj, pend, tot_e, nd = res6[0]
    out.append(f"\nAmong docs with actions (aggregate sample):")
    out.append(f"  confirmed={c} rejected={rj} pending={pend} total={tot_e} n_docs={nd}")

out_text = "\n".join(out)
print(out_text)

# Write to file as well
with open("d:/Knowledge_Map/eval/diagnose_out.txt", "w", encoding="utf-8") as f:
    f.write(out_text + "\n")

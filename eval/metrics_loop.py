#!/usr/bin/env python3
"""
Metrics Loop — непрерывный цикл замера всех 5 метрик карты знаний.

Метрики:
  NRC   — Node Replication Count: среднее кол-во статей на норм-узел
  ERC   — Edge Replication Count: среднее кол-во статей на норм-ребро
  ERA   — Entity Resolution Accuracy: % групп синонимов слитых в один norm_key
  SRR   — Subject Resolution Rate: % групп синонимов субъектов слитых в norm_key
  LPF   — Linguistic Pattern Frequency: кол-во стабильных цепочек A→B→C (>=2 статьи)
  PRI   — Pattern Reliability Index: LPF × avg_confidence
  AR    — Alignment Rate: % action.full_phrase найдено в sentence_text
  CR    — Confirmed Rate: % LEADS_TO со статусом confirmed
  NOISE — % action-нодов с мусорными объектами (по стоп-листу)

Запуск:
    cd d:\\Knowledge_Map
    d:\\Knowledge_Map\\api\\.venv\\Scripts\\python.exe eval\\metrics_loop.py

Флаги:
    --once          — один замер, потом выход
    --interval N    — пауза между замерами в секундах (default: 60)
    --sample N      — кол-во Actions для Alignment Rate (default: 2000)
    --cross-article — LPF в режиме cross-article
    --output DIR    — папка для JSON-истории (default: eval/reports/metrics_history/)
"""
import sys
import os
import argparse
import datetime
import json
import time
from pathlib import Path
from collections import defaultdict

API_DIR = Path(__file__).parent.parent / "api"
sys.path.insert(0, str(API_DIR))
EVAL_DIR = Path(__file__).parent

from neomodel import config as neomodel_config, db

NEO4J_URL = os.getenv("NEO4J_URI", "bolt://neo4j:password@127.0.0.1:7687")

# ─── Noise stop-patterns (must match action_extractor.py) ────────────────────
import re

_NOISE_VERB_SET = {
    'declare', 'warrant', 'address', 'achieve', 'examine', 'compare',
    'collect', 'ensure', 'identify', 'test', 'wash', 'meet', 'see',
    'hold', 'shed', 'offer', 'limit', 'reach',
}
_NOISE_OBJ_PAT = re.compile(
    r'\b(no conflicts? of interest|further (?:investigation|research|studies?)|'
    r'statistical significance|inclusion criteri|selection bias|'
    r'patient outcomes?|quality of life|'
    r'Table \d|Figure \d|Table S\d|Fig\.\s*\d)\b',
    re.IGNORECASE,
)


# ─── Metric computations ─────────────────────────────────────────────────────

def measure_alignment_rate(sample: int = 2000) -> dict:
    """AR: % of actions where full_phrase found in sentence_text."""
    r, _ = db.cypher_query(f"""
        MATCH (a:Action)
        WHERE a.full_phrase IS NOT NULL AND a.sentence_text IS NOT NULL
        WITH a LIMIT {sample}
        RETURN
          sum(CASE WHEN a.sentence_text CONTAINS a.full_phrase THEN 1 ELSE 0 END) AS aligned,
          count(a) AS total
    """)
    aligned, total = r[0]
    return {"aligned": int(aligned), "total": int(total), "rate": aligned / total if total else 0.0}


def measure_confirmed_rate() -> dict:
    """CR: confirmed / total LEADS_TO edges."""
    r, _ = db.cypher_query("""
        MATCH ()-[r:LEADS_TO]->()
        RETURN
          sum(CASE WHEN r.status = 'confirmed' THEN 1 ELSE 0 END) AS confirmed,
          count(r) AS total
    """)
    confirmed, total = r[0]
    return {"confirmed": int(confirmed), "total": int(total), "rate": confirmed / total if total else 0.0}


def measure_nrc() -> dict:
    """NRC: per-norm_key distribution of doc_id counts."""
    r, _ = db.cypher_query("""
        MATCH (a:Action)
        WHERE a.norm_key IS NOT NULL AND a.doc_id IS NOT NULL
        WITH a.norm_key AS nk, count(DISTINCT a.doc_id) AS n_docs
        RETURN
          avg(n_docs)   AS avg_docs,
          max(n_docs)   AS max_docs,
          sum(CASE WHEN n_docs >= 2 THEN 1 ELSE 0 END) AS multi_doc,
          count(nk)     AS total
    """)
    avg, mx, multi, total = r[0]
    return {
        "avg": float(avg or 0),
        "max": int(mx or 0),
        "multi_doc_nodes": int(multi or 0),
        "total_nodes": int(total or 0),
        "multi_rate": (multi / total) if total else 0.0,
    }


def measure_erc() -> dict:
    """ERC: per-(src_nk, tgt_nk) distribution of doc_id counts."""
    r, _ = db.cypher_query("""
        MATCH (a1:Action)-[r:LEADS_TO]->(a2:Action)
        WHERE a1.norm_key IS NOT NULL AND a2.norm_key IS NOT NULL AND r.doc_id IS NOT NULL
        WITH a1.norm_key AS src, a2.norm_key AS tgt, count(DISTINCT r.doc_id) AS n_docs
        RETURN
          avg(n_docs)   AS avg_docs,
          max(n_docs)   AS max_docs,
          sum(CASE WHEN n_docs >= 2 THEN 1 ELSE 0 END) AS multi_doc,
          count(*)      AS total
    """)
    avg, mx, multi, total = r[0]
    return {
        "avg": float(avg or 0),
        "max": int(mx or 0),
        "multi_doc_edges": int(multi or 0),
        "total_edges": int(total or 0),
        "multi_rate": (multi / total) if total else 0.0,
    }


def measure_lpf(cross_article: bool = False, min_articles: int = 2) -> dict:
    """LPF/PRI: stable causal chains across corpus."""
    sys.path.insert(0, str(EVAL_DIR))
    from pattern_frequency import (
        fetch_confirmed_edges, build_adjacency,
        _extract_chains_clean, _extract_chains_cross_article,
    )
    edges = fetch_confirmed_edges()
    if not edges:
        return {"stable_chains": 0, "total_chains": 0, "top_pri": 0.0}

    patterns = {}
    adj, edge_index = build_adjacency(edges)
    if cross_article:
        _extract_chains_cross_article(adj, edge_index, patterns, max_length=4)
    else:
        _extract_chains_clean(adj, edge_index, patterns, max_length=4)

    stable = [p for p in patterns.values() if p.doc_count >= min_articles]
    top_pri = max((p.pri for p in stable), default=0.0)
    return {
        "stable_chains": len(stable),
        "total_chains": len(patterns),
        "top_pri": float(top_pri),
        "mode": "cross_article" if cross_article else "strict",
    }


def measure_era_srr() -> dict:
    """ERA + SRR from linguistic_quality.py."""
    from linguistic_quality import compute_era, compute_srr
    era = compute_era(verbose=False)
    srr = compute_srr(verbose=False)
    return {
        "era": era["era"],
        "era_merged": era["merged_groups"],
        "era_evaluable": era["evaluable_groups"],
        "srr": srr["srr"],
        "srr_merged": srr["merged_groups"],
        "srr_total": srr["total_groups"],
    }


def measure_coverage_rate(sample_docs: int = 50) -> dict:
    """Coverage Rate: actions per 1000 chars (sampled over recent articles)."""
    r, _ = db.cypher_query(f"""
        MATCH (p:WorkerArticleProgress {{state: 'done'}})
        WHERE p.doc_id IS NOT NULL
        WITH p ORDER BY rand() LIMIT {sample_docs}
        MATCH (a:Action {{doc_id: p.doc_id}})
        WITH p.doc_id AS doc_id, count(a) AS n_actions, max(a.char_end) AS max_end
        WHERE max_end > 0
        RETURN avg(toFloat(n_actions) / max_end * 1000) AS avg_rate,
               count(doc_id) AS n_docs
    """)
    avg_rate = float(r[0][0] or 0) if r else 0.0
    n_docs = int(r[0][1] or 0) if r else 0
    return {"avg_rate": avg_rate, "sample_docs": n_docs}


def measure_dag_integrity(sample_docs: int = 20) -> dict:
    """DAG integrity: % of sampled articles with no cycles in LEADS_TO graph."""
    try:
        import networkx as nx
    except ImportError:
        return {"cycle_rate": None, "note": "networkx not installed"}

    r, _ = db.cypher_query(f"""
        MATCH (p:WorkerArticleProgress {{state: 'done'}})
        WHERE p.doc_id IS NOT NULL
        WITH p ORDER BY rand() LIMIT {sample_docs}
        RETURN p.doc_id
    """)
    doc_ids = [row[0] for row in r]
    if not doc_ids:
        return {"cycle_rate": 0.0, "sample_docs": 0, "docs_with_cycles": 0}

    docs_with_cycles = 0
    for doc_id in doc_ids:
        edges, _ = db.cypher_query("""
            MATCH (s:Action {doc_id: $doc_id})-[r:LEADS_TO {status: 'confirmed'}]->(t:Action)
            WHERE r.relation_subtype <> 'PART_OF_GOAL'
            RETURN s.uid, t.uid
        """, {"doc_id": doc_id})
        G = nx.DiGraph()
        G.add_edges_from((str(e[0]), str(e[1])) for e in edges)
        if not nx.is_directed_acyclic_graph(G):
            docs_with_cycles += 1

    cycle_rate = docs_with_cycles / len(doc_ids) if doc_ids else 0.0
    return {
        "cycle_rate": cycle_rate,
        "docs_with_cycles": docs_with_cycles,
        "sample_docs": len(doc_ids),
    }


def measure_noise(sample: int = 5000) -> dict:
    """NOISE: % of action nodes with boilerplate/meta objects."""
    r, _ = db.cypher_query(f"""
        MATCH (a:Action)
        WHERE a.verb IS NOT NULL AND a.object IS NOT NULL
        WITH a LIMIT {sample}
        RETURN a.verb AS verb, a.object AS obj
    """)
    noise = 0
    for verb, obj in r:
        if verb and verb.lower() in _NOISE_VERB_SET:
            noise += 1
            continue
        if obj and _NOISE_OBJ_PAT.search(obj):
            noise += 1
    total = len(r)
    return {"noise_count": noise, "sample": total, "rate": noise / total if total else 0.0}


# ─── Snapshot ────────────────────────────────────────────────────────────────

def take_snapshot(args) -> dict:
    ts = datetime.datetime.now().isoformat()[:19]
    print(f"\n{'='*60}")
    print(f"  METRICS SNAPSHOT  {ts}")
    print(f"{'='*60}")

    snap = {"ts": ts}

    print("AR  (Alignment Rate)...", end=" ", flush=True)
    snap["ar"] = measure_alignment_rate(args.sample)
    print(f"{snap['ar']['rate']:.1%}")

    print("CR  (Confirmed Rate)...", end=" ", flush=True)
    snap["cr"] = measure_confirmed_rate()
    print(f"{snap['cr']['rate']:.1%}")

    print("NRC (Node Replication)...", end=" ", flush=True)
    snap["nrc"] = measure_nrc()
    print(f"avg={snap['nrc']['avg']:.3f} multi={snap['nrc']['multi_doc_nodes']}/{snap['nrc']['total_nodes']}")

    print("ERC (Edge Replication)...", end=" ", flush=True)
    snap["erc"] = measure_erc()
    print(f"avg={snap['erc']['avg']:.4f} multi={snap['erc']['multi_doc_edges']}/{snap['erc']['total_edges']}")

    print("LPF/PRI (Pattern Freq)...", end=" ", flush=True)
    snap["lpf"] = measure_lpf(cross_article=args.cross_article)
    print(f"stable={snap['lpf']['stable_chains']} top_pri={snap['lpf']['top_pri']:.2f}")

    print("ERA/SRR (Ling. Quality)...", end=" ", flush=True)
    snap["era_srr"] = measure_era_srr()
    print(f"ERA={snap['era_srr']['era']:.1%} SRR={snap['era_srr']['srr']:.1%}")

    print("NOISE (Meta-actions)...", end=" ", flush=True)
    snap["noise"] = measure_noise()
    print(f"{snap['noise']['rate']:.1%} ({snap['noise']['noise_count']}/{snap['noise']['sample']})")

    print("COV  (Coverage Rate)...", end=" ", flush=True)
    snap["cov"] = measure_coverage_rate()
    print(f"{snap['cov']['avg_rate']:.2f} actions/1000chars (n={snap['cov']['sample_docs']} docs)")

    print("DAG  (Acyclicity)...", end=" ", flush=True)
    snap["dag"] = measure_dag_integrity()
    if snap["dag"].get("cycle_rate") is not None:
        print(f"{snap['dag']['docs_with_cycles']}/{snap['dag']['sample_docs']} docs have cycles")
    else:
        print(snap["dag"].get("note", "n/a"))

    return snap


def print_delta(prev: dict, curr: dict):
    """Print delta between two snapshots."""
    def delta_str(key, sub, fmt=".3f"):
        try:
            v = curr[key][sub]
            p = prev[key][sub]
            d = v - p
            sign = "+" if d >= 0 else ""
            return f"{v:{fmt}} ({sign}{d:{fmt}})"
        except Exception:
            return "?"

    print("\n  DELTA from previous snapshot:")
    print(f"  AR:    {delta_str('ar',    'rate', '.1%')}")
    print(f"  CR:    {delta_str('cr',    'rate', '.1%')}")
    print(f"  NRC:   {delta_str('nrc',   'multi_rate', '.1%')}")
    print(f"  ERC:   {delta_str('erc',   'multi_rate', '.1%')}")
    print(f"  LPF:   {delta_str('lpf',   'stable_chains', 'd')}")
    print(f"  ERA:   {delta_str('era_srr', 'era', '.1%')}")
    print(f"  SRR:   {delta_str('era_srr', 'srr', '.1%')}")
    print(f"  NOISE: {delta_str('noise', 'rate', '.1%')}")
    print(f"  COV:   {delta_str('cov', 'avg_rate', '.2f')}")
    try:
        dag_curr = curr["dag"].get("docs_with_cycles", 0)
        dag_prev = prev["dag"].get("docs_with_cycles", 0)
        print(f"  DAG:   {dag_curr} cycles ({dag_curr - dag_prev:+d})")
    except Exception:
        pass


def print_summary(snap: dict):
    """Human-readable summary with targets."""
    ar = snap["ar"]["rate"]
    cr = snap["cr"]["rate"]
    nrc_multi = snap["nrc"]["multi_rate"]
    erc_multi = snap["erc"]["multi_rate"]
    lpf = snap["lpf"]["stable_chains"]
    era = snap["era_srr"]["era"]
    srr = snap["era_srr"]["srr"]
    noise = snap["noise"]["rate"]

    def status(val, good, warn):
        if val >= good:
            return "GOOD"
        if val >= warn:
            return "WARN"
        return "CRIT"

    print("\n  STATUS:")
    print(f"  AR    {ar:.1%}   {status(ar,    0.95, 0.85)}  (target >=95%)")
    print(f"  CR    {cr:.1%}   {status(cr,    0.15, 0.05)}  (target >=15%)")
    print(f"  NRC%  {nrc_multi:.1%}   {status(nrc_multi, 0.02, 0.005)} (multi-doc nodes, target >=2%)")
    print(f"  ERC%  {erc_multi:.1%}   {status(erc_multi, 0.01, 0.001)} (multi-doc edges, target >=1%)")
    print(f"  LPF   {lpf}       {status(lpf,   10,  1)}   (target >=10 stable chains)")
    print(f"  ERA   {era:.1%}   {status(era,   0.70, 0.50)}  (target >=70%)")
    print(f"  SRR   {srr:.1%}   {status(srr,   0.80, 0.60)}  (target >=80%)")
    print(f"  NOISE {noise:.1%}   {'GOOD' if noise <= 0.05 else ('WARN' if noise <= 0.10 else 'CRIT')}  (target <=5%)")

    cov = snap["cov"]["avg_rate"]
    print(f"  COV   {cov:.2f}    {status(cov, 3.0, 1.5)}  (actions/1000chars, target >=3.0)")

    dag_rate = snap["dag"].get("cycle_rate")
    if dag_rate is not None:
        dag_ok = dag_rate == 0.0
        print(f"  DAG   {snap['dag']['docs_with_cycles']}/{snap['dag']['sample_docs']} cycles  {'GOOD' if dag_ok else 'WARN'}  (target 0 cycles)")


# ─── History ─────────────────────────────────────────────────────────────────

def save_snapshot(snap: dict, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    fname = output_dir / f"snapshot_{snap['ts'].replace(':', '-')}.json"
    fname.write_text(json.dumps(snap, indent=2, ensure_ascii=False), encoding="utf-8")

    # Append line to history.jsonl
    history_file = output_dir / "history.jsonl"
    with history_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(snap, ensure_ascii=False) + "\n")


def load_last_snapshot(output_dir: Path) -> dict | None:
    history_file = output_dir / "history.jsonl"
    if not history_file.exists():
        return None
    lines = history_file.read_text(encoding="utf-8").strip().splitlines()
    if not lines:
        return None
    try:
        return json.loads(lines[-1])
    except Exception:
        return None


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Metrics loop for Knowledge Map quality.")
    parser.add_argument("--once",        action="store_true",   help="Single measurement then exit")
    parser.add_argument("--interval",    type=int, default=60,  help="Seconds between measurements (default: 60)")
    parser.add_argument("--sample",      type=int, default=2000, help="Actions sampled for AR (default: 2000)")
    parser.add_argument("--cross-article", action="store_true", help="LPF cross-article mode")
    parser.add_argument("--output",      type=str, default=None, help="History output dir")
    args = parser.parse_args()

    output_dir = Path(args.output) if args.output else EVAL_DIR / "reports" / "metrics_history"

    neomodel_config.DATABASE_URL = NEO4J_URL
    print(f"Connected to Neo4j at {NEO4J_URL}")

    iteration = 0
    prev_snap = load_last_snapshot(output_dir)
    if prev_snap:
        print(f"Last snapshot: {prev_snap['ts']}")

    while True:
        iteration += 1
        snap = take_snapshot(args)
        print_summary(snap)
        if prev_snap:
            print_delta(prev_snap, snap)
        save_snapshot(snap, output_dir)
        prev_snap = snap

        if args.once:
            break

        print(f"\nNext snapshot in {args.interval}s  (Ctrl+C to stop)")
        try:
            time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nStopped.")
            break


if __name__ == "__main__":
    main()

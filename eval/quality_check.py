#!/usr/bin/env python3
"""
Quality evaluation script for the knowledge-map pipeline.

Samples 100 random 'done' articles from Neo4j, computes auto-metrics
(alignment, coverage, confirmed_rate, DAG integrity), and generates a
Markdown report with sampled confirmed edges for manual review.

Run from the api/ poetry environment:
    cd d:\\Knowledge_Map\\api
    poetry run python ..\\eval\\quality_check.py [--limit N] [--fix]
"""
import sys
import os
from pathlib import Path

# Bootstrap: make api/ importable (same pattern as auto_review.py)
API_DIR = Path(__file__).parent.parent / "api"
sys.path.insert(0, str(API_DIR))

import argparse
import datetime
import logging
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

import networkx as nx
from neomodel import config as neomodel_config, db

from auto_review import (
    should_confirm,
    extract_verb,
    is_bio_verb,
    is_meta_verb,
)

logging.basicConfig(level=logging.WARNING)

# ─── Configuration ────────────────────────────────────────────────────────────

NEO4J_URL = os.getenv("NEO4J_URI", "bolt://neo4j:password@127.0.0.1:7687")
SAMPLE_SIZE = 100
EDGES_PER_ARTICLE = 5
LOW_CONFIRMED_THRESHOLD = 0.15
LOW_COVERAGE_THRESHOLD = 3.0   # actions per 1000 chars


# ─── Data structures ──────────────────────────────────────────────────────────

@dataclass
class SampledEdge:
    src_phrase: str
    src_sentence: str
    tgt_phrase: str
    tgt_sentence: str
    subtype: str
    confidence: float
    evidence: list


@dataclass
class ArticleMetrics:
    pmcid: str
    doc_id: str
    action_count: int = 0
    max_char_end: int = 0
    aligned_count: int = 0
    alignment_rate: float = 0.0
    coverage_rate: float = 0.0
    confirmed_count: int = 0
    rejected_count: int = 0
    pending_count: int = 0
    confirmed_rate: float = 0.0
    subtype_dist: dict = field(default_factory=dict)
    action_class_dist: dict = field(default_factory=dict)
    has_cycle: bool = False
    cycle_detail: str = ""
    sampled_edges: list = field(default_factory=list)


# ─── Neo4j queries ────────────────────────────────────────────────────────────

def fetch_done_articles(limit: int = SAMPLE_SIZE) -> list[dict]:
    results, _ = db.cypher_query(
        """
        MATCH (p:WorkerArticleProgress {state: 'done'})
        WHERE p.doc_id IS NOT NULL
        RETURN p.pmcid AS pmcid, p.doc_id AS doc_id
        ORDER BY rand()
        LIMIT $limit
        """,
        {"limit": limit},
    )
    return [{"pmcid": r[0], "doc_id": r[1]} for r in results]


def compute_action_stats(doc_id: str) -> dict:
    """Returns action_count, max_char_end, aligned_count, action_class_dist."""
    results, _ = db.cypher_query(
        """
        MATCH (a:Action {doc_id: $doc_id})
        RETURN
            count(a) AS action_count,
            max(a.char_end) AS max_char_end,
            collect({
                full_phrase: a.full_phrase,
                sentence_text: a.sentence_text,
                action_class: a.action_class
            }) AS actions
        """,
        {"doc_id": doc_id},
    )
    if not results:
        return {"action_count": 0, "max_char_end": 0, "aligned_count": 0, "class_dist": {}}

    row = results[0]
    action_count = row[0] or 0
    max_char_end = row[1] or 0
    actions = row[2] or []

    # Python-side alignment check (safer than Cypher CONTAINS for special chars)
    aligned = sum(
        1 for a in actions
        if a.get("full_phrase") and a.get("sentence_text")
        and a["full_phrase"] in a["sentence_text"]
    )

    class_dist = dict(Counter(a.get("action_class", "action") for a in actions))

    return {
        "action_count": action_count,
        "max_char_end": max_char_end,
        "aligned_count": aligned,
        "class_dist": class_dist,
    }


def compute_edge_stats(doc_id: str) -> dict:
    """Returns confirmed, rejected, pending counts and subtype distribution."""
    results, _ = db.cypher_query(
        """
        MATCH (s:Action {doc_id: $doc_id})-[r:LEADS_TO]->(t:Action)
        WHERE r.relation_subtype <> 'PART_OF_GOAL'
        RETURN r.status AS status, r.relation_subtype AS subtype, count(r) AS cnt
        """,
        {"doc_id": doc_id},
    )
    confirmed = rejected = pending = 0
    subtype_dist: dict = {}

    for status, subtype, cnt in results:
        cnt = cnt or 0
        if status == "confirmed":
            confirmed += cnt
            if subtype:
                subtype_dist[subtype] = subtype_dist.get(subtype, 0) + cnt
        elif status == "rejected":
            rejected += cnt
        elif status == "pending":
            pending += cnt

    return {
        "confirmed": confirmed,
        "rejected": rejected,
        "pending": pending,
        "subtype_dist": subtype_dist,
    }


def fetch_sample_edges(doc_id: str, n: int = EDGES_PER_ARTICLE) -> list[SampledEdge]:
    results, _ = db.cypher_query(
        """
        MATCH (s:Action {doc_id: $doc_id})-[r:LEADS_TO {status: 'confirmed'}]->(t:Action)
        WHERE r.relation_subtype <> 'PART_OF_GOAL'
        RETURN s.full_phrase, s.sentence_text, t.full_phrase, t.sentence_text,
               r.relation_subtype, r.confidence, r.evidence
        ORDER BY rand()
        LIMIT $n
        """,
        {"doc_id": doc_id, "n": n},
    )
    edges = []
    for row in results:
        src_phrase, src_sent, tgt_phrase, tgt_sent, subtype, conf, evidence = row
        edges.append(SampledEdge(
            src_phrase=src_phrase or "",
            src_sentence=src_sent or "",
            tgt_phrase=tgt_phrase or "",
            tgt_sentence=tgt_sent or "",
            subtype=subtype or "",
            confidence=float(conf) if conf is not None else 0.0,
            evidence=list(evidence) if evidence else [],
        ))
    return edges


def check_dag_integrity(doc_id: str) -> tuple[bool, str]:
    """Returns (has_cycle, detail)."""
    results, _ = db.cypher_query(
        """
        MATCH (s:Action {doc_id: $doc_id})-[r:LEADS_TO {status: 'confirmed'}]->(t:Action {doc_id: $doc_id})
        WHERE r.relation_subtype <> 'PART_OF_GOAL'
        RETURN s.uid AS src, t.uid AS tgt
        """,
        {"doc_id": doc_id},
    )
    if not results:
        return False, ""
    G = nx.DiGraph()
    for src, tgt in results:
        G.add_edge(src, tgt)
    if nx.is_directed_acyclic_graph(G):
        return False, ""
    try:
        cycle = next(nx.simple_cycles(G))
        return True, f"cycle_len={len(cycle)}"
    except StopIteration:
        return True, "cycle_detected"


def fetch_rejected_edges(doc_id: str) -> list[dict]:
    results, _ = db.cypher_query(
        """
        MATCH (s:Action {doc_id: $doc_id})-[r:LEADS_TO {status: 'rejected'}]->(t:Action)
        WHERE r.relation_subtype <> 'PART_OF_GOAL'
        RETURN s.full_phrase, t.full_phrase, r.relation_subtype, r.confidence, r.evidence
        """,
        {"doc_id": doc_id},
    )
    return [
        {
            "src_phrase": r[0] or "",
            "tgt_phrase": r[1] or "",
            "subtype": r[2] or "",
            "confidence": float(r[3]) if r[3] is not None else 0.0,
            "evidence": list(r[4]) if r[4] else [],
        }
        for r in results
    ]


def fetch_confirmed_edges_full(doc_id: str) -> list[dict]:
    results, _ = db.cypher_query(
        """
        MATCH (s:Action {doc_id: $doc_id})-[r:LEADS_TO {status: 'confirmed'}]->(t:Action)
        WHERE r.relation_subtype <> 'PART_OF_GOAL'
        RETURN s.full_phrase, t.full_phrase, r.relation_subtype, r.confidence, r.evidence
        """,
        {"doc_id": doc_id},
    )
    return [
        {
            "src_phrase": r[0] or "",
            "tgt_phrase": r[1] or "",
            "subtype": r[2] or "",
            "confidence": float(r[3]) if r[3] is not None else 0.0,
            "evidence": list(r[4]) if r[4] else [],
        }
        for r in results
    ]


# ─── Per-article evaluation ───────────────────────────────────────────────────

def evaluate_article(pmcid: str, doc_id: str) -> ArticleMetrics:
    m = ArticleMetrics(pmcid=pmcid, doc_id=doc_id)

    # Action stats
    stats = compute_action_stats(doc_id)
    m.action_count = stats["action_count"]
    m.max_char_end = stats["max_char_end"]
    m.aligned_count = stats["aligned_count"]
    m.alignment_rate = m.aligned_count / m.action_count if m.action_count else 0.0
    m.coverage_rate = m.action_count / (m.max_char_end / 1000) if m.max_char_end > 0 else 0.0
    m.action_class_dist = stats["class_dist"]

    # Edge stats
    estats = compute_edge_stats(doc_id)
    m.confirmed_count = estats["confirmed"]
    m.rejected_count = estats["rejected"]
    m.pending_count = estats["pending"]
    reviewed = m.confirmed_count + m.rejected_count
    m.confirmed_rate = m.confirmed_count / reviewed if reviewed > 0 else 0.0
    m.subtype_dist = estats["subtype_dist"]

    # DAG integrity
    m.has_cycle, m.cycle_detail = check_dag_integrity(doc_id)

    # Sample confirmed edges for manual review
    m.sampled_edges = fetch_sample_edges(doc_id, EDGES_PER_ARTICLE)

    return m


# ─── Aggregate metrics ────────────────────────────────────────────────────────

def compute_overall_metrics(articles: list[ArticleMetrics]) -> dict:
    n = len(articles)
    total_actions = sum(m.action_count for m in articles)
    total_confirmed = sum(m.confirmed_count for m in articles)
    total_rejected = sum(m.rejected_count for m in articles)
    total_pending = sum(m.pending_count for m in articles)
    total_reviewed = total_confirmed + total_rejected

    all_subtypes: Counter = Counter()
    all_classes: Counter = Counter()
    for m in articles:
        for st, cnt in m.subtype_dist.items():
            all_subtypes[st] += cnt
        for cls, cnt in m.action_class_dist.items():
            all_classes[cls] += cnt

    articles_with_cycles = sum(1 for m in articles if m.has_cycle)
    articles_with_data = [m for m in articles if m.max_char_end > 0]

    avg_alignment = sum(m.alignment_rate for m in articles) / n if n else 0.0
    avg_coverage = (
        sum(m.coverage_rate for m in articles_with_data) / len(articles_with_data)
        if articles_with_data else 0.0
    )
    overall_confirmed_rate = total_confirmed / total_reviewed if total_reviewed else 0.0
    low_coverage = sum(1 for m in articles if 0 < m.coverage_rate < LOW_COVERAGE_THRESHOLD)
    low_confirmed = sum(1 for m in articles if m.confirmed_rate < LOW_CONFIRMED_THRESHOLD
                        and (m.confirmed_count + m.rejected_count) > 0)
    zero_actions = sum(1 for m in articles if m.action_count == 0)

    return {
        "total_articles": n,
        "total_actions": total_actions,
        "total_confirmed_edges": total_confirmed,
        "total_rejected_edges": total_rejected,
        "total_pending_edges": total_pending,
        "overall_confirmed_rate": overall_confirmed_rate,
        "avg_alignment_rate": avg_alignment,
        "avg_coverage_rate": avg_coverage,
        "articles_with_cycles": articles_with_cycles,
        "low_coverage_articles": low_coverage,
        "low_confirmed_articles": low_confirmed,
        "zero_action_articles": zero_actions,
        "subtype_distribution": dict(all_subtypes.most_common()),
        "action_class_distribution": dict(all_classes.most_common()),
    }


# ─── Failure pattern analysis ─────────────────────────────────────────────────

def _bucket_rejection_reason(reason: str) -> str:
    if "meta src verb" in reason:
        return "meta_src_verb"
    if "meta tgt verb" in reason:
        return "meta_tgt_verb"
    if "abstract shared entity" in reason:
        return "abstract_shared_entity"
    if "abstract keyword" in reason:
        return "abstract_keyword"
    if "non-bio verbs" in reason or "non-bio:" in reason:
        return "non_bio_verbs"
    if "same generic verb" in reason:
        return "same_generic_verb"
    if "no clear positive signal" in reason:
        return "no_signal"
    if "sequential non-bio" in reason:
        return "sequential_non_bio"
    if "low conf" in reason:
        return "low_confidence"
    return "other"


def analyze_failure_patterns(articles: list[ArticleMetrics]) -> dict:
    rejection_reasons: Counter = Counter()
    leaked_meta_verbs: Counter = Counter()

    for m in articles:
        # Analyse rejection reasons for low-quality articles
        if m.confirmed_rate < LOW_CONFIRMED_THRESHOLD and m.rejected_count > 0:
            rejected = fetch_rejected_edges(m.doc_id)
            for e in rejected:
                _, reason = should_confirm(
                    e["src_phrase"], e["tgt_phrase"],
                    e["subtype"], e["confidence"], e["evidence"],
                )
                rejection_reasons[_bucket_rejection_reason(reason)] += 1

        # Check confirmed edges for leaked meta-verbs
        if m.confirmed_count > 0:
            confirmed = fetch_confirmed_edges_full(m.doc_id)
            for e in confirmed:
                sv = extract_verb(e["src_phrase"])
                tv = extract_verb(e["tgt_phrase"])
                if is_meta_verb(sv):
                    leaked_meta_verbs[sv] += 1
                if is_meta_verb(tv):
                    leaked_meta_verbs[tv] += 1

    return {
        "rejection_reasons": dict(rejection_reasons.most_common()),
        "leaked_meta_verbs": leaked_meta_verbs.most_common(20),
    }


# ─── Report generation ────────────────────────────────────────────────────────

def generate_markdown_report(
    articles: list[ArticleMetrics],
    overall: dict,
    failure_patterns: dict,
    timestamp: str,
) -> str:
    lines: list[str] = []

    lines.append(f"# Knowledge Map Quality Report")
    lines.append(f"\nGenerated: {timestamp}  |  Articles sampled: {len(articles)}\n")

    # --- Section 1: Overall Aggregate Metrics ---
    lines.append("## 1. Overall Aggregate Metrics\n")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| avg_confirmed_rate | {overall['overall_confirmed_rate']*100:.1f}% |")
    lines.append(f"| avg_alignment_rate | {overall['avg_alignment_rate']*100:.1f}% |")
    lines.append(f"| avg_coverage_rate | {overall['avg_coverage_rate']:.1f} actions/1000chars |")
    lines.append(f"| total_actions | {overall['total_actions']} |")
    lines.append(f"| total_confirmed_edges | {overall['total_confirmed_edges']} |")
    lines.append(f"| total_rejected_edges | {overall['total_rejected_edges']} |")
    lines.append(f"| total_pending_edges | {overall['total_pending_edges']} |")
    lines.append(f"| articles_with_cycles | {overall['articles_with_cycles']} |")
    lines.append(f"| low_coverage_articles (<{LOW_COVERAGE_THRESHOLD}) | {overall['low_coverage_articles']} |")
    lines.append(f"| low_confirmed_articles (<{LOW_CONFIRMED_THRESHOLD:.0%}) | {overall['low_confirmed_articles']} |")
    lines.append(f"| zero_action_articles | {overall['zero_action_articles']} |")

    # --- Section 2: Per-Article Summary ---
    lines.append("\n## 2. Per-Article Summary\n")
    lines.append("| # | PMCID | Actions | Coverage | Aligned% | Confirmed% | Edges(C/R/P) | Cycle |")
    lines.append("|---|-------|---------|----------|----------|------------|--------------|-------|")
    for i, m in enumerate(articles, 1):
        cycle_flag = f"CYCLE({m.cycle_detail})" if m.has_cycle else "OK"
        lines.append(
            f"| {i} | {m.pmcid} | {m.action_count} | "
            f"{m.coverage_rate:.1f} | {m.alignment_rate*100:.0f}% | "
            f"{m.confirmed_rate*100:.0f}% | "
            f"{m.confirmed_count}/{m.rejected_count}/{m.pending_count} | {cycle_flag} |"
        )

    # --- Section 3: Relation Subtype Distribution ---
    lines.append("\n## 3. Relation Subtype Distribution (confirmed edges)\n")
    lines.append("| Subtype | Count |")
    lines.append("|---------|-------|")
    for st, cnt in overall["subtype_distribution"].items():
        lines.append(f"| {st} | {cnt} |")

    # --- Section 4: Action Class Distribution ---
    lines.append("\n## 4. Action Class Distribution\n")
    lines.append("| Class | Count |")
    lines.append("|-------|-------|")
    for cls, cnt in overall["action_class_distribution"].items():
        lines.append(f"| {cls} | {cnt} |")

    # --- Section 5: Failure Pattern Analysis ---
    lines.append("\n## 5. Failure Pattern Analysis\n")
    lines.append("### Top rejection reasons (articles with confirmed_rate < 15%)\n")
    lines.append("| Reason | Count |")
    lines.append("|--------|-------|")
    for reason, cnt in failure_patterns["rejection_reasons"].items():
        lines.append(f"| {reason} | {cnt} |")

    if failure_patterns["leaked_meta_verbs"]:
        lines.append("\n### Leaked meta-verbs in confirmed edges\n")
        lines.append("| Verb | Count |")
        lines.append("|------|-------|")
        for verb, cnt in failure_patterns["leaked_meta_verbs"]:
            lines.append(f"| {verb} | {cnt} |")

    # --- Section 6: Sample Edges for Manual Review ---
    lines.append("\n## 6. Sample Edges for Manual Review\n")
    lines.append(
        "_Для каждого ребра: **P** (plausible — реальная биологическая связь), "
        "**N** (noise — мусор), **U** (uncertain — неясно)._\n"
    )
    lines.append(
        "_Финальная оценка precision = P / (P + N) по всей выборке._\n"
    )

    articles_with_edges = [m for m in articles if m.sampled_edges]
    for m in articles_with_edges:
        lines.append(
            f"\n<details>\n"
            f"<summary>Article {m.pmcid} ({m.doc_id[:8]}…) — "
            f"confirmed_rate={m.confirmed_rate*100:.0f}%, "
            f"actions={m.action_count}, "
            f"confirmed_edges={m.confirmed_count}</summary>\n"
        )
        lines.append("| # | Source phrase | → | Target phrase | Subtype | Conf | Evidence |")
        lines.append("|---|--------------|---|---------------|---------|------|----------|")
        for i, e in enumerate(m.sampled_edges, 1):
            src = (e.src_phrase or "")[:70].replace("|", "/")
            tgt = (e.tgt_phrase or "")[:70].replace("|", "/")
            evidence_str = ("; ".join(e.evidence or []))[:80].replace("|", "/")
            conf_str = f"{e.confidence:.2f}"
            lines.append(
                f"| {i} | {src} | → | {tgt} | {e.subtype} | {conf_str} | {evidence_str} |"
            )
        lines.append("")
        # Source sentences below the table
        for i, e in enumerate(m.sampled_edges, 1):
            src_sent = (e.src_sentence or "")[:250]
            tgt_sent = (e.tgt_sentence or "")[:250]
            if src_sent:
                lines.append(f"> **Edge {i} src:** {src_sent}")
            if tgt_sent and tgt_sent != src_sent:
                lines.append(f"> **Edge {i} tgt:** {tgt_sent}")
            if src_sent or tgt_sent:
                lines.append("")
        lines.append("</details>\n")

    return "\n".join(lines)


# ─── Console summary ──────────────────────────────────────────────────────────

def print_summary(overall: dict, articles: list[ArticleMetrics]) -> None:
    sep = "=" * 62
    print(f"\n{sep}")
    print("  KNOWLEDGE MAP QUALITY EVALUATION — SUMMARY")
    print(sep)
    print(f"  Articles sampled:       {overall['total_articles']}")
    print(f"  Total actions:          {overall['total_actions']}")
    print(f"  Total confirmed edges:  {overall['total_confirmed_edges']}")
    print(f"  Total rejected edges:   {overall['total_rejected_edges']}")
    print(f"  Overall confirmed_rate: {overall['overall_confirmed_rate']*100:.1f}%")
    print(f"  Avg alignment_rate:     {overall['avg_alignment_rate']*100:.1f}%")
    print(f"  Avg coverage_rate:      {overall['avg_coverage_rate']:.1f} actions/1000chars")
    print(f"  Articles with cycles:   {overall['articles_with_cycles']}")
    print(f"  Low coverage articles:  {overall['low_coverage_articles']}")
    print(f"  Zero-action articles:   {overall['zero_action_articles']}")
    print(sep)

    # Top 5 worst articles by confirmed_rate
    worst = sorted(
        [m for m in articles if (m.confirmed_count + m.rejected_count) > 0],
        key=lambda m: m.confirmed_rate,
    )[:5]
    if worst:
        print("\n  Bottom 5 articles by confirmed_rate:")
        for m in worst:
            print(
                f"    {m.pmcid:20s}  confirmed={m.confirmed_rate*100:.0f}%  "
                f"actions={m.action_count}  edges={m.confirmed_count}C/{m.rejected_count}R"
            )

    # Subtype distribution
    print("\n  Subtype distribution (confirmed edges):")
    for st, cnt in overall["subtype_distribution"].items():
        bar = "#" * min(cnt // 5, 40)
        print(f"    {st:20s} {cnt:5d}  {bar}")
    print(sep + "\n")


# ─── Optional --fix mode ──────────────────────────────────────────────────────

def fix_low_quality_articles(articles: list[ArticleMetrics]) -> None:
    from auto_review import run as ar_run
    fixed = 0
    for m in articles:
        if m.confirmed_rate < LOW_CONFIRMED_THRESHOLD and m.pending_count > 0:
            print(f"  Re-running auto_review for {m.pmcid} ({m.doc_id[:8]}…)")
            result = ar_run(m.doc_id, dry_run=False)
            print(f"    → confirmed={result['confirmed']}, rejected={result['rejected']}")
            fixed += 1
    if fixed == 0:
        print("  No articles needed re-review (no pending edges below threshold).")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Quality check for the knowledge-map pipeline",
    )
    parser.add_argument(
        "--limit", type=int, default=SAMPLE_SIZE,
        help=f"Number of articles to sample (default: {SAMPLE_SIZE})",
    )
    parser.add_argument(
        "--fix", action="store_true",
        help="Re-run auto_review for articles with confirmed_rate below threshold",
    )
    parser.add_argument(
        "--output-dir", type=Path,
        default=Path(__file__).parent / "reports",
        help="Directory for Markdown reports (default: eval/reports/)",
    )
    args = parser.parse_args()

    # Connect neomodel (same pattern as auto_review.py)
    neomodel_config.DATABASE_URL = NEO4J_URL

    # Ensure output directory exists
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Sample articles
    print(f"Sampling up to {args.limit} 'done' articles from Neo4j…")
    articles_raw = fetch_done_articles(args.limit)
    if not articles_raw:
        print("ERROR: No 'done' articles found in Neo4j. Is the worker finished?")
        sys.exit(1)
    print(f"Sampled {len(articles_raw)} articles\n")

    # 2. Evaluate each article
    metrics: list[ArticleMetrics] = []
    for i, a in enumerate(articles_raw, 1):
        print(
            f"[{i:3d}/{len(articles_raw)}] {a['pmcid']:20s}",
            end=" ", flush=True,
        )
        m = evaluate_article(a["pmcid"], a["doc_id"])
        metrics.append(m)
        cycle_flag = " CYCLE!" if m.has_cycle else ""
        print(
            f"actions={m.action_count:4d}  "
            f"alignment={m.alignment_rate*100:.0f}%  "
            f"confirmed={m.confirmed_rate*100:.0f}%  "
            f"cov={m.coverage_rate:.1f}{cycle_flag}"
        )

    # 3. Aggregate
    overall = compute_overall_metrics(metrics)

    # 4. Failure analysis
    print("\nAnalysing failure patterns…")
    failure_patterns = analyze_failure_patterns(metrics)

    # 5. Console summary
    print_summary(overall, metrics)

    # 6. Write Markdown report
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = args.output_dir / f"quality_report_{timestamp}.md"
    report_text = generate_markdown_report(metrics, overall, failure_patterns, timestamp)
    report_path.write_text(report_text, encoding="utf-8")
    print(f"Report written to: {report_path}\n")

    # 7. Optional fix
    if args.fix:
        print("Re-running auto_review for low-quality articles (--fix)…")
        fix_low_quality_articles(metrics)


if __name__ == "__main__":
    main()

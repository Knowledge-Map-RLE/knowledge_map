#!/usr/bin/env python3
"""
Linguistic Pattern Frequency (LPF) and Pattern Reliability Index (PRI) metrics.

Metrics:
  LPF — counts how many distinct articles contain each causal chain pattern
        (sequences of norm_keys connected by LEADS_TO edges, length 2-4).
        A pattern is "stable" if chain_doc_count >= STABLE_THRESHOLD.
  PRI — weighted reliability score per pattern:
        PRI = chain_doc_count × mean(confidence of edges in chain)

Output:
  - Top-N stable patterns with LPF and PRI scores
  - Per-norm_key stable_pattern_count (how many stable patterns pass through a node)
  - Per-edge stable_pattern_count (how many stable patterns include this edge)
  - Markdown report

Run from the api/ poetry environment:
    cd d:\\Knowledge_Map\\api
    poetry run python ..\\eval\\pattern_frequency.py [--top N] [--min-articles K]
"""
import sys
import os
import argparse
import datetime
import logging
from pathlib import Path
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

API_DIR = Path(__file__).parent.parent / "api"
sys.path.insert(0, str(API_DIR))

from neomodel import config as neomodel_config, db

logging.basicConfig(level=logging.WARNING)

NEO4J_URL = os.getenv("NEO4J_URI", "bolt://neo4j:password@127.0.0.1:7687")
STABLE_THRESHOLD = 2      # min articles to call a pattern "stable"
DEFAULT_TOP = 30
MAX_CHAIN_LENGTH = 4      # max hops in a chain (edges, not nodes)


# ─── Data structures ──────────────────────────────────────────────────────────

@dataclass
class ChainPattern:
    """A causal chain A→B→...→Z defined by a tuple of norm_keys."""
    norm_keys: tuple           # e.g. (nk_A, nk_B, nk_C)
    doc_ids: set = field(default_factory=set)
    edge_confidences: list = field(default_factory=list)  # avg confidence per edge in chain

    @property
    def length(self) -> int:
        return len(self.norm_keys) - 1

    @property
    def doc_count(self) -> int:
        return len(self.doc_ids)

    @property
    def avg_confidence(self) -> float:
        return sum(self.edge_confidences) / len(self.edge_confidences) if self.edge_confidences else 0.0

    @property
    def pri(self) -> float:
        """Pattern Reliability Index = doc_count × avg_confidence."""
        return self.doc_count * self.avg_confidence

    def is_stable(self) -> bool:
        return self.doc_count >= STABLE_THRESHOLD


# ─── Neo4j queries ─────────────────────────────────────────────────────────────

def fetch_confirmed_edges() -> list[dict]:
    """
    Returns all confirmed LEADS_TO edges with norm_keys, doc_id, and confidence.
    Groups by (src_norm_key, tgt_norm_key, doc_id) to get per-article edge instances.
    """
    query = """
    MATCH (a1:Action)-[r:LEADS_TO {status: 'confirmed'}]->(a2:Action)
    WHERE a1.norm_key IS NOT NULL AND a2.norm_key IS NOT NULL
      AND a1.norm_key <> a2.norm_key
    RETURN a1.norm_key AS src_nk,
           a2.norm_key AS tgt_nk,
           r.doc_id    AS doc_id,
           r.confidence AS confidence
    """
    results, _ = db.cypher_query(query)
    edges = []
    for row in results:
        src_nk, tgt_nk, doc_id, confidence = row
        edges.append({
            "src": str(src_nk),
            "tgt": str(tgt_nk),
            "doc_id": str(doc_id) if doc_id else "unknown",
            "confidence": float(confidence) if confidence is not None else 0.0,
        })
    return edges


def build_adjacency(edges: list[dict]) -> dict:
    """
    Build adjacency map: src_nk → list of {tgt, doc_id, confidence}.
    Also build reverse index: (src_nk, tgt_nk) → list of {doc_id, confidence}.
    """
    adj: dict[str, list[dict]] = defaultdict(list)
    edge_index: dict[tuple, list[dict]] = defaultdict(list)

    for e in edges:
        adj[e["src"]].append({"tgt": e["tgt"], "doc_id": e["doc_id"], "confidence": e["confidence"]})
        edge_index[(e["src"], e["tgt"])].append({"doc_id": e["doc_id"], "confidence": e["confidence"]})

    return dict(adj), dict(edge_index)


# ─── Pattern extraction ────────────────────────────────────────────────────────

def extract_chains(edges: list[dict], max_length: int = MAX_CHAIN_LENGTH) -> dict[tuple, ChainPattern]:
    """
    Enumerate all chains of length 2..max_length hops.
    For each chain, track which doc_ids it appears in (all edges must share a doc_id).
    Returns dict: norm_key_tuple → ChainPattern.
    """
    adj, edge_index = build_adjacency(edges)

    patterns: dict[tuple, ChainPattern] = {}

    def dfs(path: list[str], path_doc_ids: set, path_confidences: list[float]):
        """DFS from current tail of path, extending by one hop at a time."""
        tail = path[-1]
        if len(path) >= 2:
            key = tuple(path)
            if key not in patterns:
                patterns[key] = ChainPattern(norm_keys=key)
            p = patterns[key]
            for doc_id in path_doc_ids:
                p.doc_ids.add(doc_id)
            # Average edge confidences for this chain occurrence
            if path_confidences:
                avg = sum(path_confidences) / len(path_confidences)
                p.edge_confidences.append(avg)

        if len(path) - 1 >= max_length:
            return

        if tail not in adj:
            return

        for next_edge in adj[tail]:
            tgt = next_edge["tgt"]
            if tgt in path:
                continue  # no cycles

            # Intersect doc_ids: chain must exist in the same article
            step_docs = {item["doc_id"] for item in edge_index.get((tail, tgt), [])}
            shared_docs = path_doc_ids & step_docs if path_doc_ids else step_docs

            if not shared_docs:
                continue

            # Average confidence for the new edge
            step_confs = [item["confidence"] for item in edge_index.get((tail, tgt), [])]
            avg_step_conf = sum(step_confs) / len(step_confs) if step_confs else 0.0

            dfs(path + [tgt], shared_docs, path_confidences + [avg_step_conf])

    # Start DFS from every node that has outgoing edges
    for src_nk in adj:
        start_docs = {e["doc_id"] for e in adj[src_nk]}
        dfs([src_nk], set(), [])  # doc_ids computed during edge traversal

    # Re-run with proper per-edge doc tracking (fix: doc_ids must be shared per path)
    # Rebuild cleanly
    patterns.clear()
    _extract_chains_clean(adj, edge_index, patterns, max_length)
    return patterns


def _extract_chains_clean(
    adj: dict,
    edge_index: dict,
    patterns: dict,
    max_length: int,
):
    """DFS tracking doc_id *intersection* at each step.

    Conservative mode: a chain A→B→C is only counted for articles where ALL
    edges appear. Use this when corpus is large and topically homogeneous.
    """

    def dfs(path: list[str], doc_ids: set, confidences: list[float]):
        if len(path) >= 2:
            key = tuple(path)
            if key not in patterns:
                patterns[key] = ChainPattern(norm_keys=key)
            p = patterns[key]
            for d in doc_ids:
                p.doc_ids.add(d)
            if confidences:
                p.edge_confidences.append(sum(confidences) / len(confidences))

        if len(path) - 1 >= max_length:
            return

        tail = path[-1]
        if tail not in adj:
            return

        for next_hop in adj[tail]:
            tgt = next_hop["tgt"]
            if tgt in path:
                continue

            edge_instances = edge_index.get((tail, tgt), [])
            step_docs = {e["doc_id"] for e in edge_instances}
            shared = doc_ids & step_docs if doc_ids else step_docs
            if not shared:
                continue

            step_conf = [e["confidence"] for e in edge_instances if e["doc_id"] in shared]
            avg_conf = sum(step_conf) / len(step_conf) if step_conf else 0.0

            dfs(path + [tgt], shared, confidences + [avg_conf])

    for src_nk in adj:
        first_level_docs = {e["doc_id"] for e in adj.get(src_nk, [])}
        dfs([src_nk], first_level_docs, [])


def _extract_chains_cross_article(
    adj: dict,
    edge_index: dict,
    patterns: dict,
    max_length: int,
):
    """DFS using edge-level doc support instead of path-level intersection.

    Cross-article mode: a chain A→B→C is stable if each individual edge
    (A→B and B→C) appears in at least STABLE_THRESHOLD articles, regardless
    of whether the same article contains the whole chain.

    This is more permissive and useful when:
    - Corpus is topically diverse (different articles cover different sub-mechanisms)
    - Individual edges are well-supported but rarely co-occur in one article

    Pattern doc_count = harmonic mean of per-edge doc counts (penalises weak links).
    """
    from math import isfinite

    def harmonic_mean(values: list[float]) -> float:
        if not values:
            return 0.0
        try:
            return len(values) / sum(1.0 / v for v in values if v > 0)
        except ZeroDivisionError:
            return 0.0

    def dfs(path: list[str], edge_doc_counts: list[int], confidences: list[float]):
        if len(path) >= 2:
            key = tuple(path)
            h = harmonic_mean([float(c) for c in edge_doc_counts])
            if key not in patterns:
                patterns[key] = ChainPattern(norm_keys=key)
            p = patterns[key]
            # Represent cross-article support as synthetic doc_ids
            # Use float -> int ceiling as proxy doc_count stored in doc_ids set
            synthetic_count = int(h) if isfinite(h) else 0
            for i in range(synthetic_count):
                p.doc_ids.add(f"__cross__{key}__{i}")
            if confidences:
                p.edge_confidences.append(sum(confidences) / len(confidences))

        if len(path) - 1 >= max_length:
            return

        tail = path[-1]
        if tail not in adj:
            return

        for next_hop in adj[tail]:
            tgt = next_hop["tgt"]
            if tgt in path:
                continue

            edge_instances = edge_index.get((tail, tgt), [])
            if not edge_instances:
                continue

            step_doc_count = len({e["doc_id"] for e in edge_instances})
            step_conf = [e["confidence"] for e in edge_instances]
            avg_conf = sum(step_conf) / len(step_conf) if step_conf else 0.0

            dfs(path + [tgt], edge_doc_counts + [step_doc_count], confidences + [avg_conf])

    for src_nk in adj:
        dfs([src_nk], [], [])


# ─── Aggregation ──────────────────────────────────────────────────────────────

def compute_node_pattern_counts(patterns: dict[tuple, ChainPattern], min_articles: int = STABLE_THRESHOLD) -> dict[str, int]:
    """
    For each norm_key, count how many stable patterns pass through it.
    Used to annotate nodes in the UI.
    """
    counts: dict[str, int] = defaultdict(int)
    for key, p in patterns.items():
        if p.doc_count < min_articles:
            continue
        for nk in key:
            counts[nk] += 1
    return dict(counts)


def compute_edge_pattern_counts(patterns: dict[tuple, ChainPattern], min_articles: int = STABLE_THRESHOLD) -> dict[tuple, int]:
    """
    For each directed edge (src_nk, tgt_nk), count how many stable patterns include it.
    Used to annotate edges in the UI.
    """
    counts: dict[tuple, int] = defaultdict(int)
    for key, p in patterns.items():
        if p.doc_count < min_articles:
            continue
        for i in range(len(key) - 1):
            counts[(key[i], key[i + 1])] += 1
    return dict(counts)


# ─── Reporting ────────────────────────────────────────────────────────────────

def generate_report(
    patterns: dict[tuple, ChainPattern],
    node_counts: dict[str, int],
    edge_counts: dict[tuple, int],
    top_n: int = DEFAULT_TOP,
    min_articles: int = STABLE_THRESHOLD,
) -> str:
    stable = [p for p in patterns.values() if p.doc_count >= min_articles]
    stable.sort(key=lambda p: p.pri, reverse=True)

    total = len(patterns)
    n_stable = len(stable)

    lines = [
        f"# Linguistic Pattern Frequency (LPF) & Pattern Reliability Index (PRI)",
        f"",
        f"Generated: {datetime.datetime.now().isoformat()[:19]}",
        f"",
        f"## Summary",
        f"",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total chain patterns found | {total} |",
        f"| Stable patterns (≥{min_articles} articles) | {n_stable} |",
        f"| Stability rate | {n_stable / total * 100:.1f}% |" if total else "| Stability rate | N/A |",
        f"| Unique nodes in stable patterns | {len(node_counts)} |",
        f"| Unique edges in stable patterns | {len(edge_counts)} |",
        f"",
        f"## Top {top_n} Patterns by PRI Score",
        f"",
        f"| Rank | Chain (norm_keys abbreviated) | Length | Articles | Avg Confidence | PRI |",
        f"|------|-------------------------------|--------|----------|---------------|-----|",
    ]

    def abbrev(nk: str) -> str:
        return nk[:12] + "…" if len(nk) > 12 else nk

    for i, p in enumerate(stable[:top_n], 1):
        chain_str = " → ".join(abbrev(nk) for nk in p.norm_keys)
        lines.append(
            f"| {i} | {chain_str} | {p.length} | {p.doc_count} | {p.avg_confidence:.2f} | {p.pri:.2f} |"
        )

    lines += [
        f"",
        f"## Top 20 Nodes by Stable Pattern Count",
        f"",
        f"| Rank | norm_key (abbreviated) | Stable patterns through node |",
        f"|------|------------------------|------------------------------|",
    ]
    top_nodes = sorted(node_counts.items(), key=lambda x: x[1], reverse=True)[:20]
    for i, (nk, cnt) in enumerate(top_nodes, 1):
        lines.append(f"| {i} | {abbrev(nk)} | {cnt} |")

    lines += [
        f"",
        f"## Top 20 Edges by Stable Pattern Count",
        f"",
        f"| Rank | src → tgt (abbreviated) | Stable patterns through edge |",
        f"|------|-------------------------|------------------------------|",
    ]
    top_edges = sorted(edge_counts.items(), key=lambda x: x[1], reverse=True)[:20]
    for i, ((src, tgt), cnt) in enumerate(top_edges, 1):
        lines.append(f"| {i} | {abbrev(src)} → {abbrev(tgt)} | {cnt} |")

    return "\n".join(lines)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Compute LPF and PRI metrics for the knowledge map.")
    parser.add_argument("--top", type=int, default=DEFAULT_TOP, help="Number of top patterns to show")
    parser.add_argument("--min-articles", type=int, default=STABLE_THRESHOLD,
                        help="Min articles for a pattern to be 'stable'")
    parser.add_argument("--max-length", type=int, default=MAX_CHAIN_LENGTH,
                        help="Max chain length in edges")
    parser.add_argument("--output", type=str, default=None,
                        help="Output Markdown file path (default: print to stdout)")
    parser.add_argument("--cross-article", action="store_true",
                        help=(
                            "Cross-article mode: a chain is stable if each individual edge "
                            "appears in >=min-articles articles, regardless of co-occurrence. "
                            "Use this for topically diverse corpora where full chains rarely "
                            "appear in a single article."
                        ))
    args = parser.parse_args()

    min_articles = args.min_articles

    neomodel_config.DATABASE_URL = NEO4J_URL
    print(f"Connecting to Neo4j at {NEO4J_URL}...")

    print("Fetching confirmed edges...")
    edges = fetch_confirmed_edges()
    print(f"  Found {len(edges)} confirmed edge instances across all articles.")

    if not edges:
        print("No confirmed edges found. Is the database populated?")
        return

    mode = "cross-article" if args.cross_article else "strict (intersection)"
    print(f"Extracting chains (max length={args.max_length}, mode={mode})...")
    patterns: dict[tuple, ChainPattern] = {}
    adj, edge_index = build_adjacency(edges)
    if args.cross_article:
        _extract_chains_cross_article(adj, edge_index, patterns, args.max_length)
    else:
        _extract_chains_clean(adj, edge_index, patterns, args.max_length)
    print(f"  Found {len(patterns)} chain patterns.")

    stable = [p for p in patterns.values() if p.doc_count >= min_articles]
    print(f"  Stable patterns (>={min_articles} articles): {len(stable)}")

    node_counts = compute_node_pattern_counts(patterns, min_articles)
    edge_counts = compute_edge_pattern_counts(patterns, min_articles)

    report = generate_report(patterns, node_counts, edge_counts, top_n=args.top, min_articles=min_articles)

    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
        print(f"Report written to {args.output}")
    else:
        print("\n" + report)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Automatic synonym discovery for knowledge map entity/verb normalization.

Approach:
  1. Pull all distinct (verb, object) pairs from Neo4j Action nodes.
  2. Embed each phrase using the spaCy model (en_core_sci_scibert).
  3. Cluster by cosine similarity > SIMILARITY_THRESHOLD.
  4. Output candidate synonym groups ranked by cluster size.
  5. Print ready-to-paste Python dict entries for VERB_SYNONYMS / ENTITY_SYNONYMS.

Run from the api/ poetry environment (needs spaCy model installed):
    cd d:\\Knowledge_Map\\api
    poetry run python ..\\eval\\discover_synonyms.py [--threshold 0.90] [--min-size 2] [--top 50]

Requirements:
    poetry add numpy scikit-learn  (if not already present)
    spaCy model: en_core_sci_scibert (loaded via nlp service)
"""
import sys
import os
import argparse
import logging
from pathlib import Path
from collections import defaultdict

import numpy as np

API_DIR = Path(__file__).parent.parent / "api"
NLP_DIR = Path(__file__).parent.parent / "nlp" / "src"
sys.path.insert(0, str(API_DIR))
sys.path.insert(0, str(NLP_DIR))

from neomodel import config as neomodel_config, db

logging.basicConfig(level=logging.WARNING)

NEO4J_URL = os.getenv("NEO4J_URI", "bolt://neo4j:password@127.0.0.1:7687")

SIMILARITY_THRESHOLD = 0.90   # cosine similarity to group as synonyms
MIN_CLUSTER_SIZE = 2           # minimum phrases in a group to report
DEFAULT_TOP = 50               # top N clusters to show
MAX_PHRASES = 5000             # cap to avoid OOM on large corpora


# ─── Fetch phrases from Neo4j ─────────────────────────────────────────────────

def fetch_object_phrases(limit: int = MAX_PHRASES) -> list[str]:
    """Return distinct object_text values from Action nodes."""
    results, _ = db.cypher_query(
        f"MATCH (a:Action) WHERE a.object IS NOT NULL AND a.object <> '' "
        f"RETURN DISTINCT a.object AS obj LIMIT {limit}"
    )
    return [str(r[0]).strip().lower() for r in results if r[0]]


def fetch_verb_phrases(limit: int = MAX_PHRASES) -> list[str]:
    """Return distinct verb (lemma) values from Action nodes."""
    results, _ = db.cypher_query(
        f"MATCH (a:Action) WHERE a.verb IS NOT NULL AND a.verb <> '' "
        f"RETURN DISTINCT a.verb AS verb LIMIT {limit}"
    )
    return [str(r[0]).strip().lower() for r in results if r[0]]


# ─── Embedding ────────────────────────────────────────────────────────────────

def load_spacy_model():
    """Load the scientific spaCy model."""
    try:
        import spacy
        nlp = spacy.load("en_core_sci_scibert")
        print("Loaded en_core_sci_scibert")
        return nlp
    except Exception:
        pass
    try:
        import spacy
        nlp = spacy.load("en_core_web_md")
        print("Loaded en_core_web_md (fallback — accuracy lower)")
        return nlp
    except Exception:
        print("ERROR: No spaCy model found. Install en_core_sci_scibert or en_core_web_md.")
        sys.exit(1)


def embed_phrases(phrases: list[str], nlp) -> np.ndarray:
    """Return embedding matrix (N x D) for a list of phrases."""
    vecs = []
    batch_size = 256
    for i in range(0, len(phrases), batch_size):
        batch = phrases[i: i + batch_size]
        docs = list(nlp.pipe(batch, disable=["ner", "parser", "tagger"]))
        for doc in docs:
            if doc.has_vector and doc.vector_norm > 0:
                vecs.append(doc.vector / doc.vector_norm)  # L2-normalised
            else:
                vecs.append(np.zeros(nlp.vocab.vectors_length or 768, dtype=np.float32))
    return np.array(vecs, dtype=np.float32)


# ─── Clustering ───────────────────────────────────────────────────────────────

def cosine_similarity_matrix(embeddings: np.ndarray) -> np.ndarray:
    """Compute full cosine similarity matrix (assumes L2-normalised input)."""
    # Already normalised → dot product = cosine similarity
    return embeddings @ embeddings.T


def greedy_cluster(phrases: list[str], embeddings: np.ndarray, threshold: float) -> list[list[str]]:
    """
    Greedy single-linkage clustering by cosine similarity.
    Each phrase joins the first cluster whose centroid is >= threshold.
    Returns list of clusters (each cluster is a list of phrases).
    """
    n = len(phrases)
    assigned = [-1] * n
    centroids: list[np.ndarray] = []
    clusters: list[list[int]] = []

    for i in range(n):
        best_cluster = -1
        best_sim = threshold - 1e-9  # must beat threshold

        for ci, centroid in enumerate(centroids):
            sim = float(np.dot(embeddings[i], centroid))
            if sim > best_sim:
                best_sim = sim
                best_cluster = ci

        if best_cluster >= 0:
            clusters[best_cluster].append(i)
            # Update centroid (running mean)
            members = clusters[best_cluster]
            centroids[best_cluster] = embeddings[members].mean(axis=0)
            norm = np.linalg.norm(centroids[best_cluster])
            if norm > 0:
                centroids[best_cluster] /= norm
            assigned[i] = best_cluster
        else:
            clusters.append([i])
            centroids.append(embeddings[i].copy())
            assigned[i] = len(clusters) - 1

    return [[phrases[idx] for idx in cluster] for cluster in clusters]


# ─── Output formatting ────────────────────────────────────────────────────────

def format_cluster_report(clusters: list[list[str]], label: str, top_n: int) -> str:
    # Filter and sort by size
    large = [c for c in clusters if len(c) >= MIN_CLUSTER_SIZE]
    large.sort(key=len, reverse=True)

    lines = [
        f"## {label} Synonym Clusters (threshold={SIMILARITY_THRESHOLD})",
        f"",
        f"Found {len(large)} groups with >= {MIN_CLUSTER_SIZE} members.",
        f"",
    ]

    for i, cluster in enumerate(large[:top_n], 1):
        canonical = cluster[0]  # most common / first
        members = cluster[1:]
        lines.append(f"### Group {i} (size={len(cluster)})")
        lines.append(f"  Canonical: **{canonical}**")
        lines.append(f"  Members: {', '.join(members)}")
        lines.append(f"  ```python")
        for m in members:
            # Escape for dict key
            lines.append(f'    "{m}": "{canonical}",')
        lines.append(f"  ```")
        lines.append("")

    return "\n".join(lines)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Discover synonym candidates via embedding clustering.")
    parser.add_argument("--threshold", type=float, default=SIMILARITY_THRESHOLD,
                        help="Cosine similarity threshold for grouping (default: 0.90)")
    parser.add_argument("--min-size", type=int, default=MIN_CLUSTER_SIZE,
                        help="Minimum cluster size to report (default: 2)")
    parser.add_argument("--top", type=int, default=DEFAULT_TOP,
                        help="Number of top clusters to show per category")
    parser.add_argument("--mode", choices=["objects", "verbs", "both"], default="both",
                        help="Which phrase type to cluster (default: both)")
    parser.add_argument("--output", type=str, default=None,
                        help="Output Markdown file (default: print to stdout)")
    parser.add_argument("--max-phrases", type=int, default=MAX_PHRASES,
                        help="Max distinct phrases to embed per category")
    args = parser.parse_args()

    global SIMILARITY_THRESHOLD, MIN_CLUSTER_SIZE
    SIMILARITY_THRESHOLD = args.threshold
    MIN_CLUSTER_SIZE = args.min_size

    neomodel_config.DATABASE_URL = NEO4J_URL
    print(f"Connecting to Neo4j at {NEO4J_URL}...")

    nlp = load_spacy_model()

    report_parts = []

    if args.mode in ("objects", "both"):
        print(f"Fetching object phrases (limit={args.max_phrases})...")
        objects = fetch_object_phrases(args.max_phrases)
        # Deduplicate while preserving order
        seen = set()
        objects = [p for p in objects if not (p in seen or seen.add(p))]
        print(f"  {len(objects)} distinct object phrases.")

        if objects:
            print("Embedding object phrases...")
            obj_emb = embed_phrases(objects, nlp)
            print("Clustering...")
            obj_clusters = greedy_cluster(objects, obj_emb, args.threshold)
            report_parts.append(format_cluster_report(obj_clusters, "Entity/Object", args.top))

    if args.mode in ("verbs", "both"):
        print(f"Fetching verb phrases (limit={args.max_phrases})...")
        verbs = fetch_verb_phrases(args.max_phrases)
        seen = set()
        verbs = [p for p in verbs if not (p in seen or seen.add(p))]
        print(f"  {len(verbs)} distinct verb lemmas.")

        if verbs:
            print("Embedding verb phrases...")
            verb_emb = embed_phrases(verbs, nlp)
            print("Clustering...")
            verb_clusters = greedy_cluster(verbs, verb_emb, args.threshold)
            report_parts.append(format_cluster_report(verb_clusters, "Verb", args.top))

    report = "\n\n".join(report_parts)

    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
        print(f"Report written to {args.output}")
    else:
        print("\n" + report)


if __name__ == "__main__":
    main()

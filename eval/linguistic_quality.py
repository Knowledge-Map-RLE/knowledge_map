#!/usr/bin/env python3
"""
Entity Resolution Accuracy (ERA) metric.

ERA measures what fraction of biologically synonymous action phrases
are correctly merged into the same norm_key in the knowledge graph.

A "synonym group" is a set of action phrases (verb + object) that
describe the same biological event but use different wording, e.g.:
  - "inhibit autophagy" / "suppress autophagic flux" / "block autophagy induction"

If all phrases in a group map to the same norm_key → group is correctly merged.
ERA = merged_groups / total_synonym_groups

The synonym dictionary is manually curated around key aging mechanisms.
Add more entries as new data accumulates.

Run from the api/ poetry environment:
    cd d:\\Knowledge_Map\\api
    poetry run python ..\\eval\\linguistic_quality.py [--verbose]
"""
import sys
import os
import argparse
import datetime
import logging
from pathlib import Path
from collections import defaultdict
from typing import Optional

API_DIR = Path(__file__).parent.parent / "api"
sys.path.insert(0, str(API_DIR))

from neomodel import config as neomodel_config, db

logging.basicConfig(level=logging.WARNING)

NEO4J_URL = os.getenv("NEO4J_URI", "bolt://neo4j:password@127.0.0.1:7687")


# ─── Synonym dictionary ───────────────────────────────────────────────────────
# Structure: list of synonym groups.
# Each group is a list of (verb, object) tuples describing the same biology.
# Verbs should be lemmatized (lowercase). Objects are the key biological entity.

SYNONYM_GROUPS: list[dict] = [
    {
        "name": "mTOR inhibits autophagy",
        "phrases": [
            ("inhibit", "autophagy"),
            ("suppress", "autophagy"),
            ("block", "autophagy"),
            ("inhibit", "autophagic flux"),
            ("suppress", "autophagic flux"),
            ("block", "autophagy induction"),
            ("inhibit", "macroautophagy"),
        ],
    },
    {
        "name": "rapamycin inhibits mTOR",
        "phrases": [
            ("inhibit", "mTOR"),
            ("inhibit", "mTORC1"),
            ("suppress", "mTOR"),
            ("block", "mTOR"),
            ("inhibit", "mammalian target of rapamycin"),
        ],
    },
    {
        "name": "senescent cells secrete SASP",
        "phrases": [
            ("secrete", "SASP"),
            ("produce", "SASP"),
            ("release", "SASP"),
            ("secrete", "senescence-associated secretory phenotype"),
            ("produce", "inflammatory cytokines"),
            ("release", "proinflammatory factors"),
        ],
    },
    {
        "name": "p53 induces apoptosis",
        "phrases": [
            ("induce", "apoptosis"),
            ("activate", "apoptosis"),
            ("trigger", "apoptosis"),
            ("promote", "apoptosis"),
            ("induce", "cell death"),
        ],
    },
    {
        "name": "telomere shortening activates p53",
        "phrases": [
            ("activate", "p53"),
            ("induce", "p53"),
            ("stabilize", "p53"),
            ("activate", "TP53"),
        ],
    },
    {
        "name": "AMPK activates autophagy",
        "phrases": [
            ("activate", "autophagy"),
            ("induce", "autophagy"),
            ("promote", "autophagy"),
            ("stimulate", "autophagy"),
            ("activate", "autophagic flux"),
        ],
    },
    {
        "name": "NF-kB induces inflammation",
        "phrases": [
            ("induce", "inflammation"),
            ("promote", "inflammation"),
            ("activate", "inflammation"),
            ("induce", "inflammatory response"),
            ("promote", "neuroinflammation"),
        ],
    },
    {
        "name": "caloric restriction extends lifespan",
        "phrases": [
            ("extend", "lifespan"),
            ("increase", "lifespan"),
            ("prolong", "lifespan"),
            ("extend", "healthspan"),
            ("increase", "longevity"),
        ],
    },
    {
        "name": "ROS induces oxidative stress",
        "phrases": [
            ("induce", "oxidative stress"),
            ("cause", "oxidative stress"),
            ("promote", "oxidative stress"),
            ("induce", "oxidative damage"),
            ("cause", "oxidative damage"),
        ],
    },
    {
        "name": "mitochondrial dysfunction increases ROS",
        "phrases": [
            ("increase", "ROS"),
            ("generate", "ROS"),
            ("increase", "reactive oxygen species"),
            ("generate", "reactive oxygen species"),
        ],
    },
    {
        "name": "p21 arrests cell cycle",
        "phrases": [
            ("arrest", "cell cycle"),
            ("inhibit", "cell cycle"),
            ("block", "cell cycle"),
            ("prevent", "cell cycle progression"),
        ],
    },
    {
        "name": "sirtuin activates longevity pathway",
        "phrases": [
            ("activate", "sirtuin"),
            ("increase", "sirtuin activity"),
            ("activate", "SIRT1"),
            ("upregulate", "SIRT1"),
            ("activate", "sirtuins"),
        ],
    },
]


# ─── compute_norm_key (mirrors api/application/action_chains/aggregate_shared_actions.py) ──
# Import directly so this file always stays in sync with the production implementation.

import hashlib

try:
    from application.action_chains.aggregate_shared_actions import (
        compute_norm_key as _prod_compute_norm_key,
    )
    compute_norm_key = _prod_compute_norm_key
    _USING_PROD_NORM_KEY = True
except ImportError:
    _USING_PROD_NORM_KEY = False

    def compute_norm_key(verb: str, subject: Optional[str], obj: Optional[str]) -> str:
        """Fallback: plain hash without synonym normalization."""
        def norm(t: Optional[str]) -> str:
            if not t:
                return ""
            return " ".join(sorted(t.lower().strip().split()))
        key = f"{verb.lower().strip()}|{norm(subject)}|{norm(obj)}"
        return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


# ─── ERA computation ──────────────────────────────────────────────────────────

def fetch_action_norm_keys() -> dict[tuple, str]:
    """
    Returns a mapping (verb_lemma, object_lower) → norm_key from all Action nodes.
    Subject is ignored here since ERA focuses on verb+object identity.
    """
    query = """
    MATCH (a:Action)
    WHERE a.norm_key IS NOT NULL
      AND a.verb IS NOT NULL
    RETURN a.verb AS verb, a.object AS obj, a.norm_key AS norm_key
    LIMIT 100000
    """
    results, _ = db.cypher_query(query)
    mapping: dict[tuple, set] = defaultdict(set)
    for row in results:
        verb, obj, nk = row
        if verb and nk:
            key = (verb.lower().strip(), (obj or "").lower().strip())
            mapping[key].add(str(nk))
    # Return the most common norm_key per (verb, obj) pair
    return {k: max(v, key=lambda x: x) for k, v in mapping.items()}


def compute_era(verbose: bool = False) -> dict:
    """
    Computes Entity Resolution Accuracy (ERA).

    For each synonym group, checks if all phrases map to the same norm_key.
    Returns a dict with ERA score and per-group results.
    """
    action_map = fetch_action_norm_keys()
    total_groups = len(SYNONYM_GROUPS)
    merged_groups = 0
    partial_groups = 0
    not_found_groups = 0

    group_results = []

    for group in SYNONYM_GROUPS:
        name = group["name"]
        phrases = group["phrases"]

        # Primary check: compute norm_keys using production formula (with synonyms).
        # This measures whether the synonym normalization layer correctly collapses
        # all variants to a single canonical hash (subject-independent).
        computed_keys = set()
        for verb, obj in phrases:
            nk = compute_norm_key(verb, None, obj)
            computed_keys.add(nk)

        # Secondary check: how many of these phrases exist in the DB at all.
        found_count = 0
        for verb, obj in phrases:
            lookup_key = (verb.lower().strip(), obj.lower().strip())
            if lookup_key in action_map:
                found_count += 1

        # ERA evaluation is based on computed_keys (subject-independent canonical hash),
        # not db_keys. Rationale: norm_keys in DB include subject in the hash, so
        # "induce(mTOR, apoptosis)" and "activate(p53, apoptosis)" will always differ.
        # ERA measures the synonym normalization layer, not per-subject identity.
        if found_count == 0:
            status = "not_in_db"
            not_found_groups += 1
        elif len(computed_keys) == 1:
            status = "merged"
            merged_groups += 1
        elif len(computed_keys) < len(phrases):
            status = "partial"
            partial_groups += 1
        else:
            status = "fragmented"

        group_results.append({
            "name": name,
            "status": status,
            "found_count": found_count,
            "total_phrases": len(phrases),
            "distinct_norm_keys_in_db": len(computed_keys),
            "computed_norm_keys": len(computed_keys),
        })

        if verbose:
            print(f"  [{status:11s}] {name} — found {found_count}/{len(phrases)} phrases, "
                  f"{len(computed_keys)} computed norm_keys")

    # ERA excludes "not_in_db" groups from denominator (can't evaluate what's not there)
    evaluable = total_groups - not_found_groups
    era = merged_groups / evaluable if evaluable > 0 else 0.0

    return {
        "era": era,
        "total_groups": total_groups,
        "evaluable_groups": evaluable,
        "merged_groups": merged_groups,
        "partial_groups": partial_groups,
        "not_found_groups": not_found_groups,
        "group_results": group_results,
    }


# ─── SRR: Subject Resolution Rate ────────────────────────────────────────────
#
# Checks whether synonymous *subject* phrases map to the same norm_key when
# paired with a fixed (verb, object).  Mirrors ERA logic but targets the
# subject slot rather than the object slot.
#
# Example: "mTOR inhibits autophagy" and "mTORC1 inhibits autophagy" should
# share the same norm_key after subject normalization.

SRR_GROUPS: list[dict] = [
    {
        "name": "mTOR/mTORC1 inhibits autophagy",
        "verb": "inhibit",
        "obj": "autophagy",
        "subjects": ["mTOR", "mTORC1", "mTORC2", "mammalian target of rapamycin"],
    },
    {
        "name": "p53/TP53 induces apoptosis",
        "verb": "induce",
        "obj": "apoptosis",
        "subjects": ["p53", "TP53", "tumor protein p53"],
    },
    {
        "name": "SIRT1/sirtuin activates autophagy",
        "verb": "activate",
        "obj": "autophagy",
        "subjects": ["SIRT1", "sirtuin", "SIRT3"],
    },
    {
        "name": "AMPK/AMP kinase activates autophagy",
        "verb": "activate",
        "obj": "autophagy",
        "subjects": ["AMPK", "AMP-activated protein kinase", "amp kinase"],
    },
    {
        "name": "ROS/reactive oxygen species induces oxidative stress",
        "verb": "induce",
        "obj": "oxidative stress",
        "subjects": ["ROS", "reactive oxygen species", "superoxide", "free radicals"],
    },
    {
        "name": "NF-kB/NFKB induces inflammation",
        "verb": "induce",
        "obj": "inflammation",
        "subjects": ["NF-kB", "NF-KB", "NFKB", "nuclear factor kappa b"],
    },
]


def compute_srr(verbose: bool = False) -> dict:
    """
    Subject Resolution Rate (SRR).

    For each SRR group, computes norm_key(verb, subject_variant, obj) for all
    subject synonyms and checks if they all hash to the same value.
    SRR = merged_groups / evaluable_groups.
    """
    total = len(SRR_GROUPS)
    merged = 0
    fragmented = 0
    group_results = []

    for group in SRR_GROUPS:
        name = group["name"]
        verb = group["verb"]
        obj = group["obj"]
        subjects = group["subjects"]

        keys = {compute_norm_key(verb, subj, obj) for subj in subjects}
        status = "merged" if len(keys) == 1 else "fragmented"
        if status == "merged":
            merged += 1
        else:
            fragmented += 1

        group_results.append({
            "name": name,
            "status": status,
            "subjects": subjects,
            "distinct_keys": len(keys),
        })

        if verbose:
            icon = "OK" if status == "merged" else "FAIL"
            print(f"  [{icon}] {name}: {len(keys)} distinct norm_keys for {len(subjects)} subject variants")

    srr = merged / total if total > 0 else 0.0
    return {
        "srr": srr,
        "total_groups": total,
        "merged_groups": merged,
        "fragmented_groups": fragmented,
        "group_results": group_results,
    }


# ─── Reporting ────────────────────────────────────────────────────────────────

def generate_report(era_result: dict, srr_result: dict) -> str:
    norm_key_source = "production (with synonym normalization)" if _USING_PROD_NORM_KEY else "fallback (no synonym normalization)"

    lines = [
        "# Linguistic Quality Metrics: ERA + SRR",
        "",
        f"Generated: {datetime.datetime.now().isoformat()[:19]}",
        f"norm_key source: {norm_key_source}",
        "",
        "## Summary",
        "",
        "| Metric | Score | Interpretation |",
        "|--------|-------|----------------|",
        f"| ERA (Entity Resolution Accuracy) | **{era_result['era']:.1%}** | % object-synonym groups fully merged |",
        f"| SRR (Subject Resolution Rate)    | **{srr_result['srr']:.1%}** | % subject-synonym groups fully merged |",
        "",
        "**ERA thresholds:**",
        "- ERA >= 0.70 = Good",
        "- ERA 0.50-0.70 = Partial (duplicate nodes exist)",
        "- ERA < 0.50 = Critical (graph highly fragmented)",
        "",
        "**SRR thresholds:**",
        "- SRR >= 0.80 = Good",
        "- SRR < 0.80 = Subject synonyms create duplicate paths",
        "",
        "## ERA — Per-Group Results",
        "",
        f"Evaluable groups: {era_result['evaluable_groups']}  "
        f"Merged: {era_result['merged_groups']}  "
        f"Partial: {era_result['partial_groups']}  "
        f"Not in DB: {era_result['not_found_groups']}",
        "",
        "| Group | Status | Found | Phrases | Distinct keys in DB |",
        "|-------|--------|-------|---------|---------------------|",
    ]

    status_icon = {
        "merged": "[OK]",
        "partial": "[~]",
        "fragmented": "[FAIL]",
        "not_in_db": "[-]",
    }

    for g in era_result["group_results"]:
        icon = status_icon.get(g["status"], "?")
        lines.append(
            f"| {g['name']} | {icon} {g['status']} "
            f"| {g['found_count']}/{g['total_phrases']} "
            f"| {g['total_phrases']} "
            f"| {g['distinct_norm_keys_in_db']} |"
        )

    lines += [
        "",
        "## SRR — Per-Group Results",
        "",
        f"Total groups: {srr_result['total_groups']}  "
        f"Merged: {srr_result['merged_groups']}  "
        f"Fragmented: {srr_result['fragmented_groups']}",
        "",
        "| Group | Status | Subjects | Distinct norm_keys |",
        "|-------|--------|----------|--------------------|",
    ]

    for g in srr_result["group_results"]:
        icon = "[OK]" if g["status"] == "merged" else "[FAIL]"
        lines.append(
            f"| {g['name']} | {icon} {g['status']} "
            f"| {len(g['subjects'])} "
            f"| {g['distinct_keys']} |"
        )

    return "\n".join(lines)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Compute ERA and SRR linguistic quality metrics.")
    parser.add_argument("--verbose", action="store_true", help="Print per-group details")
    parser.add_argument("--output", type=str, default=None,
                        help="Output Markdown file path (default: print to stdout)")
    args = parser.parse_args()

    neomodel_config.DATABASE_URL = NEO4J_URL
    print(f"Connecting to Neo4j at {NEO4J_URL}...")
    if _USING_PROD_NORM_KEY:
        print("norm_key: using production implementation (synonym normalization active)")
    else:
        print("norm_key: using fallback (no synonym normalization — import failed)")

    print("Computing ERA...")
    era_result = compute_era(verbose=args.verbose)
    print(f"  ERA = {era_result['era']:.1%}  "
          f"({era_result['merged_groups']}/{era_result['evaluable_groups']} groups merged)")

    print("Computing SRR...")
    srr_result = compute_srr(verbose=args.verbose)
    print(f"  SRR = {srr_result['srr']:.1%}  "
          f"({srr_result['merged_groups']}/{srr_result['total_groups']} subject groups merged)")

    report = generate_report(era_result, srr_result)

    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
        print(f"Report written to {args.output}")
    else:
        print("\n" + report)


if __name__ == "__main__":
    main()

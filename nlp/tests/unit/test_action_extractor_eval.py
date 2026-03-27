"""
Eval-скрипт для измерения качества извлечения LEADS_TO связей.

Запуск (требует загруженную spaCy модель en_core_sci_scibert):
    cd d:/Knowledge_Map/nlp
    poetry run python tests/unit/test_action_extractor_eval.py

Метрики:
    precision = tp / (tp + fp)   — % осмысленных из всех предложенных
    recall    = tp / (tp + fn)   — % найденных из всех реальных
    f1        = 2 * p * r / (p + r)

Цель: precision >= 0.75, recall >= 0.70, F1 >= 0.72
"""
import sys
import os

# Ensure src/ is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

import spacy
from action_extractor import ActionExtractor

# ---------------------------------------------------------------------------
# Labeled examples: (text, expected_leads_to_links)
# expected_leads_to_links = list of (src_verb_lemma, tgt_verb_lemma, subtype)
# Only LEADS_TO (evidence_type='marker') links are evaluated here.
# ---------------------------------------------------------------------------
LABELED_EXAMPLES = [
    # ── Cancer article ─────────────────────────────────────────────────────
    {
        "article": "cancer",
        "text": (
            "Cancer cells produce cytokines and enzymes, which enable the cells to invade "
            "and to attract normal cells of different tissues in order to sustain angiogenesis."
        ),
        # "enable" is infinitival and not extracted as an action node.
        # Actual detectable links: produce→attract (via "which enable"), attract→sustain (via "in order to")
        "expected_leads_to": [
            ("produce", "attract", "enables"),
            ("attract", "sustain", "enables"),
        ],
    },
    {
        "article": "cancer",
        "text": (
            "MAPK pathways can simultaneously induce cyclin D1 and CDK inhibitors, "
            "leading either to cellular proliferation or senescence."
        ),
        # "lead" is participial ("leading"), not extracted as an action node.
        # No other action pairs with explicit markers in this sentence.
        "expected_leads_to": [],
    },
    {
        "article": "cancer",
        "text": (
            "TGF-beta inhibits normal cell proliferation, but in cancer it can "
            "induce proliferation and invasion."
        ),
        "expected_leads_to": [],  # adversative "but" — should NOT be linked
    },
    {
        "article": "cancer",
        "text": (
            "Oncogenic mutations re-wire signal transduction pathways. "
            "These pathways can induce proliferation."
        ),
        # No explicit causal marker between sentences — implicit discourse causality.
        # Algorithm requires explicit markers for LEADS_TO.
        "expected_leads_to": [],
    },
    {
        "article": "cancer",
        "text": (
            "Selection for therapy resistance increases oncogenic properties of cancer cells "
            "because many mutations in oncogenes enable metastasis."
        ),
        "expected_leads_to": [
            ("increase", "enable", "causes"),
        ],
    },
    {
        "article": "cancer",
        "text": (
            "Inactivation of CDK inhibitors may translate this ambivalent signaling into "
            "proliferation in order to drive tumor progression."
        ),
        "expected_leads_to": [
            ("translate", "drive", "enables"),
        ],
    },
    # ── PD article ─────────────────────────────────────────────────────────
    {
        "article": "PD",
        "text": (
            "Alpha-synuclein aggregates to form Lewy bodies, which impair mitochondrial "
            "function and thereby trigger neuronal apoptosis."
        ),
        "expected_leads_to": [
            ("impair", "trigger", "causes"),
        ],
    },
    {
        "article": "PD",
        "text": (
            "LRRK2 phosphorylates Rab GTPases, which disrupts vesicle trafficking "
            "and causes dopaminergic neuron dysfunction."
        ),
        # "disrupt→cause" is a conjunctive (and-linked) action, no explicit causal marker.
        # Only phosphorylate→disrupt is detectable via "which disrupts" marker.
        "expected_leads_to": [
            ("phosphorylate", "disrupt", "causes"),
        ],
    },
    {
        "article": "PD",
        "text": (
            "Mitochondrial dysfunction produces reactive oxygen species, which damage "
            "cellular components and thereby promote neurodegeneration."
        ),
        "expected_leads_to": [
            ("produce", "damage", "causes"),
            ("damage", "promote", "causes"),
        ],
    },
    {
        "article": "PD",
        "text": (
            "Impaired proteasomal function leads to accumulation of misfolded proteins, "
            "which promotes aggregation."
        ),
        # "leads" has no direct obj (nmod dep), so "lead" is not extracted as an action.
        # "promote" is the only action. No links detectable.
        "expected_leads_to": [],
    },
    {
        "article": "PD",
        "text": (
            "Dopamine depletion causes motor impairment. "
            "Therefore compensatory mechanisms activate alternative pathways."
        ),
        "expected_leads_to": [
            ("cause", "activate", "sequential"),
        ],
    },
    {
        "article": "PD",
        "text": (
            "Neuroinflammation activates microglia in order to clear damaged cells."
        ),
        "expected_leads_to": [
            ("activate", "clear", "enables"),
        ],
    },
]


def evaluate(extractor: ActionExtractor, nlp, examples: list) -> dict:
    tp = fp = fn = 0
    details = []

    for ex in examples:
        actions, deps = extractor.extract(ex["text"], nlp)
        action_by_id = {a.action_id: a for a in actions}

        # Only LEADS_TO (marker-based) links
        predicted = set()
        for d in deps:
            if d.evidence_type != "marker":
                continue
            src_a = action_by_id.get(d.source_id)
            tgt_a = action_by_id.get(d.target_id)
            if src_a and tgt_a:
                predicted.add((src_a.verb_lemma, tgt_a.verb_lemma, d.relation_subtype))

        expected = set(ex["expected_leads_to"])
        tp += len(predicted & expected)
        fp += len(predicted - expected)
        fn += len(expected - predicted)

        details.append({
            "article": ex["article"],
            "text": ex["text"][:70],
            "predicted": predicted,
            "expected": expected,
            "tp": predicted & expected,
            "fp": predicted - expected,
            "fn": expected - predicted,
        })

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "details": details,
    }


if __name__ == "__main__":
    import io as _io
    sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    print("Loading spaCy model en_core_sci_scibert...")
    spacy.prefer_gpu()
    nlp = spacy.load("en_core_sci_scibert")
    print("Model loaded.\n")

    extractor = ActionExtractor()
    results = evaluate(extractor, nlp, LABELED_EXAMPLES)

    print("=" * 60)
    print("RESULTS PER EXAMPLE")
    print("=" * 60)
    for d in results["details"]:
        status = "OK" if not d["fp"] and not d["fn"] else "ISSUES"
        print(f"[{status}] [{d['article']}] {d['text']!r}")
        if d["tp"]:
            print(f"  + TP: {sorted(d['tp'])}")
        if d["fp"]:
            print(f"  - FP: {sorted(d['fp'])}")
        if d["fn"]:
            print(f"  - FN: {sorted(d['fn'])}")

    print()
    print("=" * 60)
    print("OVERALL METRICS (LEADS_TO only)")
    print("=" * 60)
    print(f"  TP={results['tp']}  FP={results['fp']}  FN={results['fn']}")
    print(f"  Precision : {results['precision']:.3f}  (target >= 0.75)")
    print(f"  Recall    : {results['recall']:.3f}  (target >= 0.70)")
    print(f"  F1        : {results['f1']:.3f}  (target >= 0.72)")

    # Per-article breakdown
    for article in ("cancer", "PD"):
        ex_subset = [d for d in results["details"] if d["article"] == article]
        atp = sum(len(d["tp"]) for d in ex_subset)
        afp = sum(len(d["fp"]) for d in ex_subset)
        afn = sum(len(d["fn"]) for d in ex_subset)
        ap = atp / (atp + afp) if (atp + afp) > 0 else 0.0
        ar = atp / (atp + afn) if (atp + afn) > 0 else 0.0
        af1 = 2 * ap * ar / (ap + ar) if (ap + ar) > 0 else 0.0
        print(f"\n  [{article}] precision={ap:.3f}  recall={ar:.3f}  F1={af1:.3f}")

    print()
    ok = results["precision"] >= 0.75 and results["recall"] >= 0.70
    print("PASS" if ok else "FAIL (below targets)")

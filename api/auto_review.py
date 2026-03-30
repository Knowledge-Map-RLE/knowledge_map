"""
Auto-review script for Action LEADS_TO edges.
Confirms edges where both verbs are biological mechanisms/results.
Rejects edges with meta-commentary verbs, abstract shared entities, etc.
"""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))

from neomodel import config, db

config.DATABASE_URL = 'bolt://neo4j:password@127.0.0.1:7687'

# ─── classification ───────────────────────────────────────────────────────────

BIO_VERBS = {
    # direct molecular mechanisms
    "inhibit", "activate", "phosphorylate", "bind", "regulate", "modulate",
    "catalyze", "ubiquitinate", "acetylate", "methylate", "cleave", "recruit",
    "sequester", "stabilize", "degrade", "translocate", "oligomerize",
    "aggregate", "fold", "interact", "associate", "localize", "polymerize",
    "dimerize", "hydrolyze", "oxidize", "reduce", "block", "suppress",
    "induce", "generate", "promote", "prevent", "protect", "damage",
    "cause", "produce", "enhance", "restore", "increase", "decrease",
    "improve", "attenuate", "ameliorate", "exacerbate", "accelerate",
    "delay", "arrest", "halt", "reverse", "mediate", "rescue",
    "release", "trigger", "signal", "express", "encode", "mutate",
    "impair", "disrupt", "form", "accumulate", "clear", "depolymerize",
    "upregulate", "downregulate", "methylate", "demethylate", "acetylate",
    "deacetylate", "sumoylate", "nitrosylate", "glycosylate",
    # cell/tissue-level
    "apoptose", "proliferate", "differentiate", "migrate", "infiltrate",
    "survive", "die", "necrose", "senesce",
    # disease-specific
    "aggregate", "misfold", "fibrilize", "deposit", "spread",
    "infect", "replicate", "transmit",
    # additional biological
    "yield", "reduce", "increase", "inhibit", "activate",
    "bind", "recruit", "release", "trigger", "cause", "promote",
    "prevent", "protect", "damage", "impair", "disrupt", "form",
    "accumulate", "clear", "mediate", "signal", "express",
    "encode", "mutate", "influence", "contribute", "require",
    "identify", "facilitate", "initiate", "induce", "produce",
    "counteract", "affect", "restore", "remove", "detect",
    "maintain", "drive", "stop", "turn", "further",
    # gerund/participle roots
    "causing", "producing", "triggering", "facilitating", "inducing",
    "disrupting", "affecting", "counteracting", "modulating", "inhibiting",
    "activating", "promoting", "generating", "recruiting", "releasing",
    "removing", "detecting", "maintaining", "driving", "restoring",
    # additional
    "deregulate", "dysregulate", "sensitize", "desensitize", "potentiate",
    "propagate", "transmit", "excite", "depolarize", "hyperpolarize",
    # transport/structural
    "carry", "transfer", "transport", "deliver",
    # therapeutic actions
    "substitute", "replace", "supplement",
    # cellular acquisition
    "acquire",
}

META_VERBS = {
    # meta-commentary / writing about science
    "suggest", "indicate", "show", "demonstrate", "report", "describe",
    "discuss", "review", "summarize", "conclude", "propose", "hypothesize",
    "argue", "note", "observe", "find", "found", "present", "provide",
    "examine", "investigate", "analyze", "study", "test", "measure",
    "evaluate", "assess", "compare", "consider", "highlight", "emphasize",
    "focus", "aim", "attempt", "try", "seek", "explore", "address",
    "approach", "develop", "build", "create", "design", "implement",
    "establish", "introduce", "define", "characterize", "classify",
    "categorize", "organize", "structure", "organize", "integrate",
    "incorporate", "include", "involve", "comprise", "consist", "contain",
    "represent", "reflect", "illustrate", "exemplify", "highlight",
    "demonstrate", "validate", "confirm", "verify", "support", "challenge",
    # movement/abstract
    "bring", "take", "give", "get", "go", "come", "make", "use",
    "adopt", "apply", "employ", "utilize", "leverage",
    "extend", "expand", "broaden", "narrow", "limit",
    "understand", "explain", "clarify", "elucidate", "reveal",
    "uncover", "discover", "identify_meta",
    "hasten", "facilitate_meta", "enable_meta",
    # abstract systems
    "monitor", "control", "manage", "coordinate",
    "encourage",   # "encourage peers" — social
}

# Shared-entity markers that are too abstract to be meaningful
ABSTRACT_ENTITY_TOKENS = {
    'neuron', 'neurons', 'cell', 'cells', 'protein', 'proteins',
    'gene', 'genes', 'pathway', 'pathways', 'disease', 'diseases',
    'process', 'processes', 'role', 'roles', 'function', 'functions',
    'mechanism', 'mechanisms', 'effect', 'effects', 'level', 'levels',
    'activity', 'activities', 'signal', 'signals',
    # 'response'/'responses' removed — "microglial response", "immune response" are concrete
    'factor', 'factors', 'type', 'types', 'form', 'forms',
    'feature', 'features', 'aspect', 'aspects', 'part', 'parts',
    'stage', 'stages', 'phase', 'phases', 'step', 'steps',
    'way', 'ways', 'result', 'results', 'outcome', 'outcomes',
    'change', 'changes', 'loss', 'losses', 'damage', 'damages',
    'production', 'accumulation', 'aggregation',
    # 'release' removed — "neurotransmitter release" is concrete
    # 'response' removed — "microglial response" is concrete
    # abstract concepts added in last session
    'information', 'brain', 'body', 'system', 'systems', 'model', 'models',
    'data', 'context', 'scale', 'area', 'region', 'network', 'networks',
    'hallmark', 'hallmarks', 'principle', 'principles', 'aging', 'cancer',
    'life', 'text', 'people', 'growth', 'death',
    # additional common abstracts
    'view', 'approach', 'concept', 'idea', 'theory', 'framework',
    'evidence', 'finding', 'findings', 'observation', 'observations',
    'control', 'feedback', 'loop', 'cycle', 'cascade', 'interaction',
    'environment', 'environment', 'condition', 'conditions',
    'symptom', 'symptoms', 'sign', 'signs',
    'patient', 'patients', 'subject', 'subjects',
}


import re as _re

def _normalize_verb(word: str) -> str:
    """Rough lemmatization: strip common suffixes to reach base form."""
    w = word.lower()
    # -ing: causing→cause, triggering→trigger, producing→produce
    if w.endswith('ing'):
        stem = w[:-3]
        # try stem + e: caus→cause, produc→produce, facilitat→facilitate
        if stem + 'e' in BIO_VERBS or stem + 'e' in META_VERBS:
            return stem + 'e'
        # double consonant: triggering→trigger (trigge→r→trigger)
        if len(stem) >= 2 and stem[-1] == stem[-2]:
            shorter = stem[:-1]
            if shorter in BIO_VERBS or shorter in META_VERBS:
                return shorter
        # stem itself: modulating→modulat→modulate (try +e)
        if stem in BIO_VERBS or stem in META_VERBS:
            return stem
        return stem + 'e'  # best guess
    # -en forms: driven→drive, broken→break, fallen→fall
    if w.endswith('en'):
        stem = w[:-2]
        if stem + 'e' in BIO_VERBS or stem + 'e' in META_VERBS:
            return stem + 'e'
        if stem in BIO_VERBS or stem in META_VERBS:
            return stem
        # driven→driv→drive
        return stem + 'e'
    # -ed: facilitated→facilitate, triggered→trigger, modeled→model
    if w.endswith('ed'):
        stem = w[:-2]
        if stem.endswith('e'):
            return stem
        if stem + 'e' in BIO_VERBS or stem + 'e' in META_VERBS:
            return stem + 'e'
        if len(stem) >= 2 and stem[-1] == stem[-2]:
            return stem[:-1]
        return stem
    # -s: facilitates→facilitate, inhibits→inhibit
    if w.endswith('s') and not w.endswith('ss') and len(w) > 3:
        return w[:-1]
    return w


def extract_verb(phrase: str) -> str:
    """Extract first word and normalize to lemma approximation."""
    if not phrase:
        return ""
    first = phrase.strip().split()[0].lower()
    return _normalize_verb(first)


def is_bio_verb(verb: str) -> bool:
    v = _normalize_verb(verb)
    return (v in BIO_VERBS or v + 's' in BIO_VERBS or v + 'e' in BIO_VERBS
            or v + 'es' in BIO_VERBS)


def is_meta_verb(verb: str) -> bool:
    v = _normalize_verb(verb)
    return (v in META_VERBS or v + 's' in META_VERBS or v + 'e' in META_VERBS)


def shared_entity_is_abstract(evidence: list) -> bool:
    """Check if shared entity in evidence is too abstract."""
    for ev in (evidence or []):
        if ev.startswith('[shared:'):
            entity = ev[8:].rstrip(']').strip().lower()
            # Check if entity is or contains abstract tokens
            tokens = entity.split()
            for t in tokens:
                t_clean = t.strip('.,;:')
                if t_clean in ABSTRACT_ENTITY_TOKENS:
                    return True
            # Short entities (1-2 words) that are pronouns or articles only
            if entity in {'it', 'its', 'this', 'these', 'those', 'that', 'they', 'them',
                          'the', 'a', 'an', 'their', 'our', 'its'}:
                return True
    return False


def keyword_is_abstract(evidence: list) -> bool:
    """Check if keyword/obj_obj overlap evidence is too abstract."""
    for ev in (evidence or []):
        for prefix in ('[keyword:', '[obj_obj:'):
            if ev.startswith(prefix):
                kws = ev[len(prefix):].rstrip(']').strip().lower()
                # reject if ALL shared keywords are abstract
                kw_list = [k.strip() for k in kws.split(',')]
                if all(k in ABSTRACT_ENTITY_TOKENS for k in kw_list if k):
                    return True
    return False


def should_confirm(src_phrase: str, tgt_phrase: str, relation: str,
                   confidence: float, evidence: list) -> tuple[bool, str]:
    src_verb = extract_verb(src_phrase)
    tgt_verb = extract_verb(tgt_phrase)

    # Reject if either verb is meta-commentary
    if is_meta_verb(src_verb):
        return False, f"meta src verb: {src_verb}"
    if is_meta_verb(tgt_verb):
        return False, f"meta tgt verb: {tgt_verb}"

    # Reject if shared entity is abstract
    if shared_entity_is_abstract(evidence):
        return False, f"abstract shared entity: {evidence}"

    # Reject if keyword overlap is abstract
    if keyword_is_abstract(evidence):
        return False, f"abstract keyword: {evidence}"

    # Reject if low confidence and neither verb is bio
    if confidence < 0.6 and not is_bio_verb(src_verb) and not is_bio_verb(tgt_verb):
        return False, f"low conf + non-bio verbs: {src_verb}, {tgt_verb}"

    # Reject sequential edges where neither verb is bio
    if relation == 'sequential' and not is_bio_verb(src_verb) and not is_bio_verb(tgt_verb):
        return False, f"sequential non-bio: {src_verb}, {tgt_verb}"

    src_bio = is_bio_verb(src_verb)
    tgt_bio = is_bio_verb(tgt_verb)

    # Same generic verb (cause→cause, require→require) without a real causal marker → reject
    # EXCEPT if shared subject is a concrete biological entity (gene/protein name)
    _GENERIC_BIO = {'cause', 'require', 'share', 'identify', 'contribute', 'involve'}
    if src_verb == tgt_verb and src_verb in _GENERIC_BIO:
        has_real_marker = any(ev and not ev.startswith('[') for ev in (evidence or []))
        if not has_real_marker:
            # Allow if shared subject is concrete (not abstract, not "mutations"/"cells")
            has_concrete_subject = False
            for ev in (evidence or []):
                if ev.startswith('[subject:'):
                    subj = ev[9:].rstrip(']').strip().lower()
                    tokens = subj.split(',')
                    if all(t.strip() not in ABSTRACT_ENTITY_TOKENS and t.strip() not in
                           {'mutation', 'mutations', 'variant', 'variants', 'change', 'changes',
                            'cell', 'cells', 'factor', 'factors', 'gene', 'genes',
                            'protein', 'proteins', 'pathway', 'pathways'}
                           for t in tokens if t.strip()):
                        has_concrete_subject = True
            # Also allow cause→cause via obj_obj if objects are different specific entities
            has_obj_obj_evidence = any('[obj_obj:' in str(ev) for ev in (evidence or []))
            if has_obj_obj_evidence and not keyword_is_abstract(evidence):
                has_concrete_subject = True
            if not has_concrete_subject:
                return False, f"same generic verb without marker: {src_verb}"

    # Confirm marker-based edges with at least one bio verb
    has_marker = any(ev and not ev.startswith('[') for ev in (evidence or []))
    if has_marker:
        if src_bio or tgt_bio:
            return True, "marker + bio verb"
        return False, f"marker but non-bio verbs: {src_verb}, {tgt_verb}"

    # Shared-entity edges: require both bio verbs
    has_shared = any('[shared:' in str(ev) for ev in (evidence or []))
    if has_shared:
        if src_bio and tgt_bio:
            return True, "shared entity + both bio verbs"
        return False, f"shared entity but non-bio: {src_verb}, {tgt_verb}"

    # Keyword overlap: require both bio verbs
    has_keyword = any('[keyword:' in str(ev) for ev in (evidence or []))
    if has_keyword:
        if src_bio and tgt_bio:
            return True, "keyword + both bio verbs"
        return False, f"keyword but non-bio: {src_verb}, {tgt_verb}"

    # Obj→obj overlap: require both bio verbs (weaker signal, same rule)
    has_obj_obj = any('[obj_obj:' in str(ev) for ev in (evidence or []))
    if has_obj_obj:
        if src_bio and tgt_bio:
            return True, "obj_obj + both bio verbs"
        return False, f"obj_obj but non-bio: {src_verb}, {tgt_verb}"

    # Shared subject: require both bio verbs
    has_subject = any('[subject:' in str(ev) for ev in (evidence or []))
    if has_subject:
        if src_bio and tgt_bio:
            return True, "shared subject + both bio verbs"
        return False, f"shared subject but non-bio: {src_verb}, {tgt_verb}"

    # Default: confirm if both bio verbs (any confidence)
    if src_bio and tgt_bio:
        return True, f"both bio verbs: {src_verb} + {tgt_verb}"

    return False, f"no clear positive signal: {src_verb}({'bio' if src_bio else 'meta'}), {tgt_verb}({'bio' if tgt_bio else 'meta'})"


def run(doc_id: str, dry_run: bool = False):
    results, _ = db.cypher_query('''
        MATCH (s:Action {doc_id: $doc_id})-[r:LEADS_TO {status: "pending"}]->(t:Action)
        RETURN s.uid, t.uid, s.full_phrase, t.full_phrase,
               r.relation_subtype, r.confidence, r.evidence
    ''', {'doc_id': doc_id})

    confirmed = []
    rejected = []

    for row in results:
        src_uid, tgt_uid, src_phrase, tgt_phrase, relation, confidence, evidence = row
        confidence = confidence or 0.0
        evidence = list(evidence) if evidence else []

        ok, reason = should_confirm(src_phrase, tgt_phrase, relation, confidence, evidence)

        src_short = (src_phrase or '')[:45]
        tgt_short = (tgt_phrase or '')[:45]

        if ok:
            confirmed.append((src_uid, tgt_uid, relation, src_short, tgt_short, reason))
        else:
            rejected.append((src_uid, tgt_uid, relation, src_short, tgt_short, reason))

    print(f"\n{'DRY RUN — ' if dry_run else ''}Results for doc {doc_id}:")
    print(f"  Confirmed: {len(confirmed)}")
    print(f"  Rejected:  {len(rejected)}")
    total = len(confirmed) + len(rejected)
    prec = len(confirmed) / total * 100 if total else 0
    print(f"  Precision: {prec:.0f}%\n")

    if not dry_run:
        for src_uid, tgt_uid, relation, *_ in confirmed:
            db.cypher_query('''
                MATCH (s:Action {uid: $src})-[r:LEADS_TO {relation_subtype: $rel}]->(t:Action {uid: $tgt})
                SET r.status = "confirmed"
            ''', {'src': src_uid, 'tgt': tgt_uid, 'rel': relation})

        for src_uid, tgt_uid, relation, *_ in rejected:
            db.cypher_query('''
                MATCH (s:Action {uid: $src})-[r:LEADS_TO {relation_subtype: $rel}]->(t:Action {uid: $tgt})
                SET r.status = "rejected"
            ''', {'src': src_uid, 'tgt': tgt_uid, 'rel': relation})
        print("  Status updated in Neo4j.")

    print("\n=== CONFIRMED ===")
    for _, _, rel, src, tgt, reason in confirmed:
        print(f"  [{rel}] {src} --> {tgt}  ({reason})")

    print("\n=== REJECTED ===")
    for _, _, rel, src, tgt, reason in rejected:
        print(f"  [{rel}] {src} --> {tgt}  ({reason})")


if __name__ == '__main__':
    DOC_ID = '886f1448799d4aba1076c65e059a3d58'
    DRY_RUN = '--dry' in sys.argv
    run(DOC_ID, dry_run=DRY_RUN)

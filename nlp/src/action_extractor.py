"""
ActionExtractor — извлечение действий и причинно-следственных связей из текста.

Использует уже загруженную spaCy модель (en_core_sci_scibert).

Action Score (AS) — объект ОБЯЗАТЕЛЕН:
    1.0 * has_object          (HARD GATE: dep in obj/dobj/nsubj:pass/obl — без этого не проходит)
    0.55 * has_content_verb   (POS=VERB AND lemma not in STOP_VERBS)
    0.30 * not_aux            (POS != AUX)
    0.15 * has_modifier       (dep in amod/advmod)
Threshold: AS >= 0.55  (с объектом минимум: 0+0.55+0.30 = 0.85 — всегда проходит если content_verb+объект)
Без объекта: AS = 0.0 — никогда не проходит.

Два типа зависимостей:

1. LEADS_TO (evidence_type='marker') — только при наличии явного маркера:
   - Pass 1: маркер внутри одного предложения (полный score)
   - Pass 2: маркер между boundary-парой предложений N→N+1
             (последнее действие N → первое действие N+1, штраф −0.10)
   relation_subtype определяется типом маркера (causes/enables/prevents/via_mechanism/sequential)

2. SYNTACTIC_DEP (evidence_type='syntactic') — синтаксические связи:
   - xcomp, advcl, ccomp, conj в обоих режимах (dense и sparse)
   - relation_subtype = метка зависимости spaCy (xcomp/advcl/ccomp/conj)
   - Сохраняются в отдельный тип ребра Neo4j, НЕ как LEADS_TO

Детекция режима:
    causal_density = (число сильных маркеров в тексте) / (число предложений)
    DENSE_THRESHOLD = 0.08  (менее 1 маркера на 12 предложений → слабая)
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import List

from action_markers import STRONG_MARKERS, MARKER_SUBTYPE_MAP

logger = logging.getLogger(__name__)

# Patterns that indicate an action is an artifact (DOI, copyright, table cell, hyphenation, section heading)
_ARTIFACT_PATTERNS = re.compile(
    r'^(?:'
    r'doi:\S+|'                          # DOI strings
    r'Received\s+doi|'                   # "Received doi:..."
    r'See\s+the\s+Terms|'               # copyright notice
    r'http[s]?://|'                      # URLs
    r'\w+-\s*$'                          # hyphenated word at end (line-break artifact)
    r')|'
    r'\bsee (?:Table|Figure|Supplementary|Fig\.?|S\d)\b|'  # cross-references: "see Table 1"
    r'\bsee (?:the\s+)?(?:methods?|materials?|section)\b',  # "see the methods"
    re.IGNORECASE,
)

# Action phrases that are meta-commentary or evolutionary metaphors, not biomedical mechanisms
_META_PHRASE_PATTERNS = re.compile(
    r'\bDarwinian[- ]type\b|'
    r'\bapples and oranges\b|'
    r'\bno selective advantage\b|'
    r'\bSee text\b|'
    r'^undergo\b|'           # "undergo selection" — passive metaphor, not mechanism
    r'\ba (?:new|novel|better|deeper|greater|more\s+\w+) \w+\b|'  # "a new era", "a better approach"
    r'\bthe (?:urgent|critical|key|main|primary|central) \w+\b|'  # "the urgent need", "the key challenge"
    r'\b(?:rich and complex|growing body of|body of knowledge)\b|'  # meta-narrative phrases
    r'\b(?:PD research|cancer research|aging research)\b|'          # research domain, not mechanism
    # Editorial / methods boilerplate
    r'\bno conflicts? of interest\b|'          # "declare no conflicts of interest"
    r'\bconflicts? of interest\b|'             # shorter variant
    r'\bfurther (?:investigation|research|studies?|work|analysis)\b|'  # "warrant further investigation"
    r'\bstatistical significance\b|'            # "reach statistical significance"
    r'\binclusion criteri\b|'                   # "meet the inclusion criteria"
    r'\bexclusion criteri\b|'
    r'\bselection bias\b|'                      # "introduce selection bias"
    r'\bshed (?:light|new light)\b|'            # "shed light on" — meta-narrative
    r'\bhold (?:great\s+)?promise\b|'           # "holds promise"
    r'\boffer(?:s|ed|ing)?\s+(?:valuable\s+)?insights?\b|'  # "offers valuable insights"
    r'\blimit(?:s|ed|ing)?\s+(?:our\s+)?(?:ability|generalizability|sample size)\b|'
    r'\bpatient outcomes?\b|'                   # "improve patient outcomes" — clinical endpoint, not mechanism
    r'\bquality of life\b|'                     # "improve quality of life" — endpoint
    r'\bwash(?:ed)?\s+(?:three|two|four|\d+)\s+times?\b|'  # "washed three times" — methods
    r'\bcollect(?:ed|ing)?\s+(?:data|samples?|blood|tissue)\b|'  # "collected data" — methods
    r'\bensure(?:d|s)?\s+consistency\b|'        # "ensure consistency" — methods
    r'\baddress(?:ed|es|ing)?\s+this\b|'        # "address this" — referential, no content
    r'\bachieve(?:d|s|ing)?\s+this\b|'          # "achieve this" — referential
    r'\benable(?:d|s|ing)?\s+(?:us|them|researchers?)\b',  # "enables them" — referential
    re.IGNORECASE,
)

# Object phrases that represent vague epistemic/methodological goals, not biological entities
# These are action objects that look meaningful but carry no mechanistic content
_EPISTEMIC_OBJECT_PAT = re.compile(
    r'^(?:'
    r'(?:this|these|those|it|them|us)$|'        # pure pronouns as objects
    r'(?:a|the)?\s*(?:clear|better|deeper|greater|more\s+\w+)\s+understanding\b|'
    r'(?:a|the)?\s*(?:new|comprehensive|systematic)\s+(?:framework|approach|perspective)\b|'
    r'(?:a|an|the)?\s*(?:broad|wide|key|crucial|major|significant)\s+(?:challenge|gap|question|issue|problem)\b|'
    r'(?:a|an|the)?\s*(?:important|significant|critical)\s+(?:implication|consideration|limitation)\b'
    r')',
    re.IGNORECASE,
)

# Minimum meaningful object length (chars, excluding spaces)
_MIN_OBJECT_CHARS = 4

# Stop verbs that are participial modifiers rather than true actions
_PARTICIPIAL_STOP = {
    'encode', 'lack', 'govern', 'accompany', 'comprise',
    'include', 'involve', 'contain', 'represent',
    'control',   # "controlling apoptosis" — gerund as complement, not main action
}

# Object phrases that are too vague to be meaningful actions
# e.g. "plays an important role", "plays a key role", "plays a more causal role"
_VAGUE_OBJECT_PAT = re.compile(
    r'^(?:a|an|the|this|that)?\s*(?:important|key|more\s+\w+|major|central|critical|crucial|pivotal|significant|vital)?\s*'
    r'(?:role|part|function|aspect|factor|component|element|feature)\b',
    re.IGNORECASE,
)

# Pattern: object is only determiner + single word (e.g. "an form", "a type", "the role")
# These NPs are too vague to represent a meaningful action
_WEAK_NP_PAT = re.compile(
    r'^(?:a|an|the|this|that|these|those|some|such)\s+\w+$',
    re.IGNORECASE,
)

# Pattern: object phrase starts with a common English article/determiner in Title Case
# e.g. "governed The hallmarks of..." — section heading artifact
# Specifically: verb + space + "The"/"A"/"An"/"This"/"That" + space + lowercase
_HEADING_ARTIFACT_PAT = re.compile(r'^\w+\s+(?:The|A|An|This|That|These|Those)\s+[a-z]')

STOP_VERBS = {
    'be', 'have', 'do', 'get', 'make', 'seem', 'appear', 'remain',
    'become', 'include', 'involve', 'contain', 'represent', 'constitute',
    'use', 'show', 'find', 'suggest', 'indicate', 'note', 'observe',
    'report', 'describe', 'discuss', 'present', 'provide', 'give',
    'know', 'think', 'say', 'tell', 'call', 'name', 'mean', 'refer',
    'take', 'add', 'face', 'miss', 'experience', 'deserve',
    'appreciate',  # "appreciating the progress" — meta-commentary
    'practice',    # "practicing a type" — vague
    'affect',      # "affect populations" — too vague without specific object
    'connect',     # "connect the scales" — often subordinate clause head
    'create',      # "creating an interesting challenge" — meta-commentary
    'form',        # "aggregates to form Lewy bodies" — resultative complement, not action
    # Meta-commentary: writing/thinking about science, never biological mechanisms
    'model',       # "modeled environmental causes" — computational/conceptual
    'adopt',       # "adopt this cell-based view" — meta
    'develop',     # "develop PD research" — organizational meta
    'investigate', # "investigating the enzyme" — research meta
    'monitor',     # "monitor the local environment" — surveillance, not mechanism
    'understand',  # "understand the key factors" — cognitive meta
    'hasten',      # "hasten the emergence" — vague temporal metaphor
    'coordinate',  # "coordinate interdisciplinary research" — organizational
    'lead',        # "led Braak and others" — narrative subject
    'bring',       # "bring PD research" — meta-narrative
    'pave',        # "pave the way" — metaphor, never mechanism
    'highlight',   # "highlight the importance" — meta
    'emphasize',   # "emphasize the role" — meta
    'demonstrate', # "demonstrate the mechanism" — meta (showing, not doing)
    'reveal',      # "reveal the pathway" — meta
    'support',     # "support the hypothesis" — meta
    'challenge',   # "challenge the dogma" — meta
    'encourage',   # "encourage our peers" — social/meta
    'oppose',      # "opposing a low number" — organizational
    'exert',       # "exert feedback control" — vague, never molecular
    'play',        # "play a supportive role" — vague placeholder
    'gain',        # "gain access to the brain" — vague spatial
    'exhibit',     # "exhibit hallmarks" — descriptive
    'reflect',     # "reflect the importance" — meta
    # Methods / statistics boilerplate
    'declare',     # "declare no conflicts of interest" — editorial
    'warrant',     # "warrant further investigation" — editorial conclusion
    'address',     # "address this" — referential/meta
    'achieve',     # "achieve this" — referential
    'examine',     # "examine associations" — statistical methods
    'compare',     # "compare them" — statistical methods
    'collect',     # "collect data" — methods, not mechanism
    'ensure',      # "ensure consistency" — methods
    'identify',    # "identify factors" — methods/results framing
    'test',        # "test this" — methods
    'wash',        # "washed three times" — laboratory procedure boilerplate
    'meet',        # "meet inclusion criteria" — clinical methods
    'see',         # "see Table/Figure" — cross-reference
    'hold',        # "hold promise" — evaluative meta
    'shed',        # "shed light" — narrative metaphor
    'offer',       # "offer insights" — evaluative meta
    'limit',       # "limit our ability" — limitations section boilerplate
    'reach',       # "reach statistical significance" — statistical framing
}

# Compiled marker patterns: (compiled_pattern, score, pattern_str)
# pattern_str used for MARKER_SUBTYPE_MAP lookup
_COMPILED_MARKERS = [
    (re.compile(pat, re.IGNORECASE), score, pat)
    for pat, score in STRONG_MARKERS
]

# For density detection: compile all marker patterns into a single fast regex
_ALL_MARKER_PAT = re.compile(
    '|'.join(pat for pat, _ in STRONG_MARKERS),
    re.IGNORECASE,
)

# Adversative connectors: when these appear in the gap, suppress LEADS_TO creation
_ADVERSATIVE_PAT = re.compile(
    r'\b(?:but|however|although|though|despite|whereas|yet|nevertheless|nonetheless|'
    r'on\s+the\s+other\s+hand|in\s+contrast|conversely)\b',
    re.IGNORECASE,
)

# Markdown heading lines: # Title, ## Section, ### Subsection
# Used to blank out headings before NLP parsing so heading words aren't extracted as actions
_MARKDOWN_HEADING_RE = re.compile(r'^#{1,6}\s+.+$', re.MULTILINE)

# Causal density threshold: below → sparse/weakly-connected text
DENSE_THRESHOLD = 0.08  # < 1 marker per 12 sentences

# Link score thresholds by mode
LINK_SCORE_THRESHOLD_DENSE = 0.70
LINK_SCORE_THRESHOLD_SPARSE = 0.60

# Penalty for cross-sentence (boundary-pair) marker links
_CROSS_SENTENCE_PENALTY = 0.10

# Syntactic dependency scores by dep label
_SYNTACTIC_SCORES = {
    'xcomp': 0.88,
    'advcl': 0.85,
    'ccomp': 0.80,
    'conj':  0.72,
}


@dataclass
class ExtractedAction:
    action_id: str
    verb_lemma: str
    verb_text: str
    object_text: str
    full_phrase: str
    sentence_text: str
    sentence_idx: int
    char_start: int
    char_end: int
    modifiers: List[str] = field(default_factory=list)
    action_score: float = 0.0
    subject_text: str = ""


@dataclass
class ExtractedDependency:
    source_id: str
    target_id: str
    marker_text: str
    link_score: float
    relation_subtype: str = 'causes'   # causes|enables|prevents|via_mechanism|sequential|xcomp|advcl|ccomp|conj
    evidence_type: str = 'marker'      # 'marker' | 'syntactic'
    sentence_distance: int = 0         # для отладки


def _get_object_np(token) -> tuple[str, int]:
    """Return (object NP text, last token index in doc) for a verb token.

    Returns ('', -1) if no object found.

    Tries direct object dependencies first, then falls back to
    xcomp/ccomp for verbs like 'cause', 'lead', 'result'.
    Subtree capped at 12 tokens to avoid grabbing whole clauses.
    """
    # Primary: direct object
    for child in token.children:
        if child.dep_ in ('obj', 'dobj', 'nsubj:pass'):
            # Find the cut point: first relcl/acl/appos child of the head noun
            # to avoid capturing relative clauses ("mTOR, which extends...")
            cut_i = None
            for grandchild in child.children:
                if grandchild.dep_ in ('relcl', 'acl', 'acl:relcl', 'appos'):
                    cut_i = grandchild.left_edge.i
                    break
            if cut_i is not None:
                # Return only tokens before the relative clause
                span_tokens = [t for t in child.subtree if t.i < cut_i]
                # Strip trailing punctuation/comma
                while span_tokens and span_tokens[-1].is_punct:
                    span_tokens.pop()
                if span_tokens:
                    last_i = span_tokens[-1].i
                    return child.doc[span_tokens[0].i: last_i + 1].text, last_i
                return child.text, child.i
            subtree = list(child.subtree)
            if len(subtree) > 12:
                # Return just the head + immediate determiners/adjectives
                det = next((c.text for c in child.children if c.dep_ in ('det', 'amod')), '')
                text = f"{det} {child.text}".strip() if det else child.text
                return text, child.i
            last_i = subtree[-1].i
            return child.doc[subtree[0].i: last_i + 1].text, last_i

    # Secondary: oblique argument (obl) — common in passive constructions
    for child in token.children:
        if child.dep_ == 'obl':
            subtree = list(child.subtree)
            if len(subtree) > 8:
                return child.text, child.i
            last_i = subtree[-1].i
            return child.doc[subtree[0].i: last_i + 1].text, last_i

    return '', -1


def _get_subject_np(token) -> str:
    """Return the subject NP text for a verb token, or empty string.

    Looks for nsubj (active) and nsubjpass/nsubj:pass (passive) dependencies.
    Falls back to the subject of a parent verb if the token is a subordinate clause head.
    Subtree capped at 8 tokens.
    """
    # Direct subject
    for child in token.children:
        if child.dep_ in ('nsubj', 'nsubj:pass', 'nsubjpass'):
            subtree = list(child.subtree)
            if len(subtree) > 8:
                det = next((c.text for c in child.children if c.dep_ in ('det', 'amod')), '')
                return f"{det} {child.text}".strip() if det else child.text
            return child.doc[subtree[0].i: subtree[-1].i + 1].text

    # Fallback: inherit subject from parent verb (for subordinate clause heads)
    head = token.head
    if head != token and head.pos_ in ('VERB', 'AUX'):
        for child in head.children:
            if child.dep_ in ('nsubj', 'nsubj:pass', 'nsubjpass'):
                return child.text

    return ''


def _action_score(token, obj_text: str) -> float:
    """Compute Action Score. Returns 0.0 if no object (hard gate)."""
    if not obj_text:
        return 0.0  # Hard gate: object is mandatory
    has_content_verb = 1.0 if (token.pos_ == 'VERB' and token.lemma_.lower() not in STOP_VERBS) else 0.0
    not_aux = 1.0 if token.pos_ != 'AUX' else 0.0
    has_modifier = 0.0
    has_particle = 0.0
    for child in token.children:
        if child.dep_ in ('amod', 'advmod'):
            has_modifier = 1.0
        if child.dep_ == 'prt':
            # Phrasal verb particle (e.g. "slow down", "switch off") — confirms action intent
            has_particle = 1.0
    return 0.55 * has_content_verb + 0.28 * not_aux + 0.12 * has_modifier + 0.05 * has_particle


def _compute_causal_density(text: str) -> float:
    """Compute causal marker density: markers per sentence."""
    marker_count = len(_ALL_MARKER_PAT.findall(text))
    # Simple sentence splitter
    sentences = [s for s in re.split(r'(?<=[.!?])\s+', text) if len(s.strip()) > 15]
    if not sentences:
        return 0.0
    density = marker_count / len(sentences)
    logger.debug("[action_extractor] causal_density=%.4f (%d markers / %d sents)",
                 density, marker_count, len(sentences))
    return density


def _classify_subtype(pattern_str: str) -> str:
    """Return relation_subtype for a matched marker pattern string."""
    return MARKER_SUBTYPE_MAP.get(pattern_str, 'causes')


def _search_markers_in_gap(gap_text: str, tgt_verb_text: str = '') -> tuple[float, str, str]:
    """Search for the best causal marker in gap_text.

    gap_text may include the target verb itself (to catch "which disrupts",
    "thereby trigger" patterns). When a match equals the target verb text,
    it is skipped — the target verb is not a connector.

    Returns (best_score, best_marker_text, best_pattern_str).
    Returns (0.0, '', '') if no marker found.
    """
    best_score = 0.0
    best_marker = ''
    best_pat_str = ''
    tgt_lower = tgt_verb_text.lower().strip() if tgt_verb_text else ''
    for pattern, score, pat_str in _COMPILED_MARKERS:
        m = pattern.search(gap_text)
        if not m:
            continue
        matched = m.group(0).strip()
        # Skip if the matched text is just the target verb itself (not a connector)
        if tgt_lower and matched.lower() == tgt_lower:
            continue
        if score > best_score:
            best_score = score
            best_marker = matched
            best_pat_str = pat_str
    return best_score, best_marker, best_pat_str


class ActionExtractor:
    """Extracts actions and their dependencies from text using a spaCy model."""

    def extract(self, text: str, nlp) -> tuple[list[ExtractedAction], list[ExtractedDependency]]:
        # Blank out markdown headings (## Title) to prevent heading words from being
        # extracted as actions. Replace with spaces to preserve char offsets.
        def _blank_heading(m: re.Match) -> str:
            return ' ' * len(m.group(0))
        text = _MARKDOWN_HEADING_RE.sub(_blank_heading, text)

        # Detect connectivity mode before parsing (cheap)
        causal_density = _compute_causal_density(text)
        is_sparse = causal_density < DENSE_THRESHOLD
        link_threshold = LINK_SCORE_THRESHOLD_SPARSE if is_sparse else LINK_SCORE_THRESHOLD_DENSE
        logger.info(
            "[action_extractor] mode=%s causal_density=%.4f link_threshold=%.2f",
            "SPARSE" if is_sparse else "DENSE", causal_density, link_threshold,
        )

        doc = nlp(text)
        actions: list[ExtractedAction] = []

        for sent_idx, sent in enumerate(doc.sents):
            for token in sent:
                if token.pos_ not in ('VERB', 'AUX'):
                    continue
                if token.lemma_.lower() in STOP_VERBS:
                    continue
                obj_text, obj_end_i = _get_object_np(token)
                score = _action_score(token, obj_text)
                if score < 0.55:
                    continue

                modifiers = [
                    child.text for child in token.children
                    if child.dep_ in ('amod', 'advmod', 'neg')
                ]

                subject_text = _get_subject_np(token)
                # Build full_phrase as actual doc span from verb token to end of object,
                # so phrasal verb particles (e.g. "down" in "slow down aging") are included.
                if obj_end_i >= 0:
                    full_phrase = token.doc[token.i: obj_end_i + 1].text
                else:
                    full_phrase = token.text

                # Filter: object too short to be meaningful
                if len(obj_text.replace(' ', '')) < _MIN_OBJECT_CHARS:
                    continue

                # Filter: weak NP — determiner + single word ("a type", "an form", "the role")
                if _WEAK_NP_PAT.match(obj_text):
                    continue

                # Filter: participial modifiers that aren't true actions (lemma check)
                if token.lemma_.lower() in _PARTICIPIAL_STOP:
                    continue

                # Filter: heading artifact — object starts with capital letter (e.g. "governed The hallmarks")
                if _HEADING_ARTIFACT_PAT.match(full_phrase):
                    continue

                # Filter: vague role/function object ("plays an important role", "plays a key role")
                if _VAGUE_OBJECT_PAT.match(obj_text):
                    continue

                # Filter: epistemic/methodological object (no mechanistic content)
                if _EPISTEMIC_OBJECT_PAT.match(obj_text):
                    continue

                # Filter artifacts: DOI, copyright, table cross-references, hyphenation
                if _ARTIFACT_PATTERNS.search(full_phrase):
                    continue

                # Filter meta-phrases: editorial boilerplate, evolutionary metaphors
                if _META_PHRASE_PATTERNS.search(full_phrase):
                    continue

                actions.append(ExtractedAction(
                    action_id=f"A{len(actions)}",
                    verb_lemma=token.lemma_,
                    verb_text=token.text,
                    object_text=obj_text,
                    full_phrase=full_phrase,
                    sentence_text=sent.text,
                    sentence_idx=sent_idx,
                    char_start=token.idx,
                    char_end=(token.doc[obj_end_i].idx + len(token.doc[obj_end_i].text)) if obj_end_i >= 0 else (token.idx + len(token.text)),
                    modifiers=modifiers,
                    action_score=score,
                    subject_text=subject_text,
                ))

        deps = self._extract_dependencies(actions, text, doc, link_threshold)
        logger.info(
            "[action_extractor] text_len=%d actions=%d deps=%d",
            len(text), len(actions), len(deps),
        )
        return actions, deps

    def _extract_dependencies(
        self,
        actions: list[ExtractedAction],
        text: str,
        doc,
        link_threshold: float,
    ) -> list[ExtractedDependency]:
        """Find dependencies between actions.

        Pass 1: LEADS_TO — маркер внутри одного предложения.
        Pass 2: LEADS_TO — маркер между boundary-парой предложений N→N+1 (штраф −0.10).
        Pass 3: SYNTACTIC_DEP — xcomp/advcl/ccomp/conj в обоих режимах.

        LEADS_TO создаётся ТОЛЬКО при наличии маркера.
        SYNTACTIC_DEP — отдельный тип, не конкурирует с LEADS_TO.
        """
        deps: list[ExtractedDependency] = []
        if len(actions) < 2:
            return deps

        # Build lookup: sentence_idx → list of action indices (in order)
        sent_to_actions: dict[int, list[int]] = {}
        for i, a in enumerate(actions):
            sent_to_actions.setdefault(a.sentence_idx, []).append(i)

        # Dedup set for LEADS_TO: avoid duplicate (src_id, tgt_id) — keep max score
        leads_to_best: dict[tuple[str, str], ExtractedDependency] = {}

        # ── Pass 1: LEADS_TO — marker within the same sentence ───────────────
        # Only link ADJACENT actions within a sentence (ii → ii+1).
        # Linking non-adjacent pairs (ii → ii+2+) would skip intermediate actions
        # and create false positives when a marker spans the whole sentence.
        for sent_idx, action_indices in sent_to_actions.items():
            if len(action_indices) < 2:
                continue
            for ii in range(len(action_indices) - 1):
                for jj in [ii + 1]:
                    src = actions[action_indices[ii]]
                    tgt = actions[action_indices[jj]]

                    # Search from src.char_end to tgt.char_end (inclusive of target verb)
                    # This allows markers like "which disrupts" or "thereby trigger" where
                    # the target verb is part of the marker pattern.
                    if src.char_end >= tgt.char_start:
                        continue
                    gap_text = text[src.char_end:tgt.char_end]

                    # Skip adversative contexts
                    if _ADVERSATIVE_PAT.search(gap_text):
                        continue

                    best_score, best_marker, best_pat_str = _search_markers_in_gap(gap_text, tgt.verb_text)
                    if best_score >= link_threshold:
                        key = (src.action_id, tgt.action_id)
                        dep = ExtractedDependency(
                            source_id=src.action_id,
                            target_id=tgt.action_id,
                            marker_text=best_marker,
                            link_score=best_score,
                            relation_subtype=_classify_subtype(best_pat_str),
                            evidence_type='marker',
                            sentence_distance=0,
                        )
                        if key not in leads_to_best or best_score > leads_to_best[key].link_score:
                            leads_to_best[key] = dep

        # ── Pass 2: LEADS_TO — marker between boundary pairs N→N+1 ───────────
        # Key fix: iterate over sentence boundaries, not consecutive action pairs.
        # Only link last action of sentence N with first action of sentence N+1.
        max_sent_idx = max(sent_to_actions.keys()) if sent_to_actions else 0
        for sent_n in range(max_sent_idx):
            sent_n1 = sent_n + 1
            if sent_n not in sent_to_actions or sent_n1 not in sent_to_actions:
                continue

            src = actions[sent_to_actions[sent_n][-1]]   # last action in sentence N
            tgt = actions[sent_to_actions[sent_n1][0]]   # first action in sentence N+1

            if src.char_end >= tgt.char_start:
                continue
            # For cross-sentence links, only look for markers in the text BETWEEN
            # the end of sentence N and the end of the first action in sentence N+1.
            # Specifically: search only in the second half of the gap (closer to sentence N+1)
            # to avoid markers deep inside sentence N (e.g. "because" mid-sentence) being
            # used to link to the next sentence's action.
            gap_full = text[src.char_end:tgt.char_end]
            gap_len = len(gap_full)
            # Use only the latter half of the gap (from sentence boundary onward)
            boundary_search_start = gap_len // 2
            gap_text = gap_full[boundary_search_start:]

            # Skip adversative contexts
            if _ADVERSATIVE_PAT.search(gap_text):
                continue

            best_score, best_marker, best_pat_str = _search_markers_in_gap(gap_text, tgt.verb_text)
            # Apply cross-sentence penalty
            adjusted_score = best_score - _CROSS_SENTENCE_PENALTY
            if adjusted_score >= link_threshold:
                key = (src.action_id, tgt.action_id)
                dep = ExtractedDependency(
                    source_id=src.action_id,
                    target_id=tgt.action_id,
                    marker_text=best_marker,
                    link_score=adjusted_score,
                    relation_subtype=_classify_subtype(best_pat_str),
                    evidence_type='marker',
                    sentence_distance=1,
                )
                if key not in leads_to_best or adjusted_score > leads_to_best[key].link_score:
                    leads_to_best[key] = dep

        deps.extend(leads_to_best.values())

        # ── Pass 3: SYNTACTIC_DEP — syntactic links (both modes) ─────────────
        # Build token→action_id map
        tok_to_action: dict[int, str] = {}
        for a in actions:
            for tok in doc:
                if tok.idx == a.char_start:
                    tok_to_action[tok.i] = a.action_id
                    break

        syntactic_rels = set(_SYNTACTIC_SCORES.keys())
        already_syntactic: set[tuple[str, str]] = set()

        for tok in doc:
            if tok.i not in tok_to_action:
                continue
            src_id = tok_to_action[tok.i]
            for child in tok.children:
                if child.dep_ not in syntactic_rels:
                    continue
                if child.i not in tok_to_action:
                    continue
                tgt_id = tok_to_action[child.i]
                if src_id == tgt_id:
                    continue
                # For conj: use document order (earlier token = source)
                if child.dep_ == 'conj' and child.i < tok.i:
                    src_id, tgt_id = tgt_id, src_id
                pair = (src_id, tgt_id)
                if pair in already_syntactic:
                    continue
                already_syntactic.add(pair)
                deps.append(ExtractedDependency(
                    source_id=src_id,
                    target_id=tgt_id,
                    marker_text=f"[syntactic:{child.dep_}]",
                    link_score=_SYNTACTIC_SCORES[child.dep_],
                    relation_subtype=child.dep_,
                    evidence_type='syntactic',
                    sentence_distance=0,
                ))

        # ── Pass 4: SHARED_ENTITY — object of A matches subject of B ────────
        # "Rapamycin inhibits mTOR" + "mTOR extends lifespan" → inhibits→extends
        # Filters:
        #   1. Subject must not be a pronoun (I/we/it/that/this/which/they)
        #   2. Shared entity must be short (≤4 tokens) — long NPs are too vague
        #   3. Shared entity must not contain prepositions (of/with/in/by/from/to)
        #      which indicate complex phrases rather than concrete entities
        #   4. Shared entity must not be an abstract concept word
        existing_leads_to_pairs = {(d.source_id, d.target_id) for d in leads_to_best.values()}

        _DET_RE = re.compile(r'^\s*(?:the|a|an|this|that|these|those)\s+', re.IGNORECASE)
        _PRONOUN_SUBJECTS = {'i', 'we', 'it', 'that', 'this', 'which', 'they', 'he', 'she', 'who'}
        _ENTITY_PREP = re.compile(r'\b(?:of|with|in|by|from|to|for|between|among|through)\b', re.IGNORECASE)
        _ABSTRACT_WORDS = {
            'hallmark', 'hallmarks', 'principle', 'principles', 'outcome', 'outcomes',
            'advantage', 'disadvantage', 'concept', 'notion', 'idea', 'theory',
            'approach', 'aspect', 'feature', 'property', 'characteristic',
            'selection', 'process', 'mechanism', 'function', 'role', 'type',
            'example', 'evidence', 'result', 'finding', 'observation',
            # Too generic to be meaningful shared entities
            'aging', 'cancer', 'life', 'text', 'people', 'cells', 'disease',
            'growth', 'death', 'time', 'level', 'rate', 'way', 'form', 'state',
            'information', 'brain', 'body', 'system', 'systems', 'model',
            'models', 'data', 'context', 'scale', 'area', 'region', 'network',
        }

        def _normalize(text: str) -> str:
            return _DET_RE.sub('', text).strip().lower()

        def _is_good_entity(text: str) -> bool:
            """Return True if the shared entity is a concrete biomedical entity."""
            norm = _normalize(text)
            # Too short
            if len(norm) < 3:
                return False
            tokens = norm.split()
            # Too long (vague complex NP)
            if len(tokens) > 4:
                return False
            # Contains prepositions (complex NP)
            if _ENTITY_PREP.search(norm):
                return False
            # Abstract concept words
            if any(t in _ABSTRACT_WORDS for t in tokens):
                return False
            return True

        already_shared: set[tuple[str, str]] = set()
        # Dedup by phrase pair to avoid duplicate edges when same text has multiple uids
        already_shared_phrases: set[tuple[str, str]] = set()
        for i, src_action in enumerate(actions):
            if not src_action.object_text:
                continue
            if not _is_good_entity(src_action.object_text):
                continue
            src_obj_norm = _normalize(src_action.object_text)
            for j, tgt_action in enumerate(actions):
                if i == j:
                    continue
                # No self-loops by phrase
                if src_action.full_phrase.lower() == tgt_action.full_phrase.lower():
                    continue
                if not tgt_action.subject_text:
                    continue
                # Filter pronoun subjects
                tgt_subj_norm = _normalize(tgt_action.subject_text)
                if tgt_subj_norm in _PRONOUN_SUBJECTS:
                    continue
                # Match: object of src == subject of tgt (exact or containment)
                if src_obj_norm != tgt_subj_norm and src_obj_norm not in tgt_subj_norm and tgt_subj_norm not in src_obj_norm:
                    continue
                pair = (src_action.action_id, tgt_action.action_id)
                phrase_pair = (src_action.full_phrase.lower(), tgt_action.full_phrase.lower())
                if pair in existing_leads_to_pairs or pair in already_shared:
                    continue
                if phrase_pair in already_shared_phrases:
                    continue
                already_shared.add(pair)
                already_shared_phrases.add(phrase_pair)
                deps.append(ExtractedDependency(
                    source_id=src_action.action_id,
                    target_id=tgt_action.action_id,
                    marker_text=f"[shared:{src_action.object_text}]",
                    link_score=0.75,
                    relation_subtype='enables',
                    evidence_type='shared_entity',
                    sentence_distance=abs(src_action.sentence_idx - tgt_action.sentence_idx),
                ))

        # ── Pass 5: KEYWORD_OVERLAP — shared keywords between obj of A and subj of B ──
        # Catches cases where exact match fails but entities are semantically related:
        # obj="normal mTOR signaling" + subj="mTOR" → match via keyword "mTOR"
        # obj="organ damage and functional decline" + subj="Hyperfunction" → no match (different)
        # Only content words (len>3, not stopwords) are used for matching.
        _STOP_WORDS = {
            'this', 'that', 'these', 'those', 'with', 'from', 'also', 'such',
            'both', 'each', 'more', 'most', 'some', 'same', 'only', 'very',
            'been', 'have', 'were', 'their', 'them', 'they', 'will', 'would',
            'could', 'should', 'other', 'than', 'then', 'when', 'where',
            'normal', 'initial', 'direct', 'common', 'high', 'low', 'new',
            # Too generic biomedical terms — match everything
            'signaling', 'pathways', 'pathway', 'signals', 'activity',
            'expression', 'levels', 'response', 'effects', 'impact',
            'its', 'and', 'the', 'for', 'not', 'but', 'are', 'was',
        } | _ABSTRACT_WORDS

        def _content_words(text: str) -> set:
            """Extract meaningful content words from text (min 4 chars)."""
            words = re.findall(r'\b[a-zA-Z][a-zA-Z0-9\-]{3,}\b', text.lower())
            return {w for w in words if w not in _STOP_WORDS}

        already_keyword: set[tuple[str, str]] = set()
        all_shared_pairs = already_shared_phrases.copy()

        for i, src_action in enumerate(actions):
            if not src_action.object_text:
                continue
            src_obj_words = _content_words(src_action.object_text)
            if not src_obj_words:
                continue
            for j, tgt_action in enumerate(actions):
                if i == j:
                    continue
                if src_action.full_phrase.lower() == tgt_action.full_phrase.lower():
                    continue
                if not tgt_action.subject_text:
                    continue
                tgt_subj_norm = _normalize(tgt_action.subject_text)
                if tgt_subj_norm in _PRONOUN_SUBJECTS:
                    continue
                tgt_subj_words = _content_words(tgt_action.subject_text)
                if not tgt_subj_words:
                    continue
                # Require at least one shared content word
                shared_words = src_obj_words & tgt_subj_words
                if not shared_words:
                    continue
                pair = (src_action.action_id, tgt_action.action_id)
                phrase_pair = (src_action.full_phrase.lower(), tgt_action.full_phrase.lower())
                if pair in existing_leads_to_pairs or pair in already_shared or pair in already_keyword:
                    continue
                if phrase_pair in all_shared_pairs:
                    continue
                already_keyword.add(pair)
                all_shared_pairs.add(phrase_pair)
                deps.append(ExtractedDependency(
                    source_id=src_action.action_id,
                    target_id=tgt_action.action_id,
                    marker_text=f"[keyword:{','.join(sorted(shared_words))}]",
                    link_score=0.65,  # Lower confidence than exact shared_entity
                    relation_subtype='enables',
                    evidence_type='keyword_overlap',
                    sentence_distance=abs(src_action.sentence_idx - tgt_action.sentence_idx),
                ))

        # ── Pass 6: SHARED_SUBJECT — same subject does A then B ─────────────
        # "Rapamycin inhibits mTOR" + "Rapamycin prevents cancer" → same agent
        # Only for concrete named subjects (not pronouns, not vague nouns).
        # Uses keyword overlap on subject text, same filters as Pass 5.
        # Lower confidence (0.55) since same-subject doesn't imply causation.
        already_subject: set[tuple[str, str]] = set()

        for i, src_action in enumerate(actions):
            if not src_action.subject_text:
                continue
            src_subj_norm = _normalize(src_action.subject_text)
            if src_subj_norm in _PRONOUN_SUBJECTS:
                continue
            # Require concrete subject — must pass _is_good_entity filter
            if not _is_good_entity(src_action.subject_text):
                continue
            src_subj_words = _content_words(src_action.subject_text)
            if not src_subj_words:
                continue
            for j, tgt_action in enumerate(actions):
                if i >= j:  # only forward pairs to avoid bidirectional duplicates
                    continue
                if src_action.full_phrase.lower() == tgt_action.full_phrase.lower():
                    continue
                if not tgt_action.subject_text:
                    continue
                tgt_subj_norm = _normalize(tgt_action.subject_text)
                if tgt_subj_norm in _PRONOUN_SUBJECTS:
                    continue
                if not _is_good_entity(tgt_action.subject_text):
                    continue
                tgt_subj_words = _content_words(tgt_action.subject_text)
                shared_subj_words = src_subj_words & tgt_subj_words
                if not shared_subj_words:
                    continue
                pair = (src_action.action_id, tgt_action.action_id)
                phrase_pair = (src_action.full_phrase.lower(), tgt_action.full_phrase.lower())
                if pair in existing_leads_to_pairs or pair in already_shared or pair in already_keyword or pair in already_subject:
                    continue
                if phrase_pair in all_shared_pairs:
                    continue
                already_subject.add(pair)
                all_shared_pairs.add(phrase_pair)
                deps.append(ExtractedDependency(
                    source_id=src_action.action_id,
                    target_id=tgt_action.action_id,
                    marker_text=f"[subject:{','.join(sorted(shared_subj_words))}]",
                    link_score=0.55,
                    relation_subtype='enables',
                    evidence_type='shared_subject',
                    sentence_distance=abs(src_action.sentence_idx - tgt_action.sentence_idx),
                ))

        # ── Pass 7: OBJ→OBJ keyword overlap — объект A содержит те же ключевые слова что и объект B ──
        # Покрывает случаи когда оба действия не имеют субъекта (gerund, passive)
        # но оба упоминают одну и ту же биологическую сущность в объекте.
        # Направление: action ближе к началу → action позже в тексте (по char_start).
        # Confidence 0.58 (ниже keyword_overlap 0.65 — слабее семантически).
        already_obj_obj: set[tuple[str, str]] = set()

        for i, src_action in enumerate(actions):
            if not src_action.object_text:
                continue
            src_obj_words = _content_words(src_action.object_text)
            if not src_obj_words:
                continue
            for j, tgt_action in enumerate(actions):
                if j <= i:  # только вперёд
                    continue
                if src_action.full_phrase.lower() == tgt_action.full_phrase.lower():
                    continue
                if not tgt_action.object_text:
                    continue
                tgt_obj_words = _content_words(tgt_action.object_text)
                if not tgt_obj_words:
                    continue
                shared_words = src_obj_words & tgt_obj_words
                if not shared_words:
                    continue
                pair = (src_action.action_id, tgt_action.action_id)
                phrase_pair = (src_action.full_phrase.lower(), tgt_action.full_phrase.lower())
                if pair in existing_leads_to_pairs or pair in already_shared or pair in already_keyword or pair in already_subject or pair in already_obj_obj:
                    continue
                if phrase_pair in all_shared_pairs:
                    continue
                already_obj_obj.add(pair)
                all_shared_pairs.add(phrase_pair)
                deps.append(ExtractedDependency(
                    source_id=src_action.action_id,
                    target_id=tgt_action.action_id,
                    marker_text=f"[obj_obj:{','.join(sorted(shared_words))}]",
                    link_score=0.58,
                    relation_subtype='enables',
                    evidence_type='obj_obj_overlap',
                    sentence_distance=abs(src_action.sentence_idx - tgt_action.sentence_idx),
                ))

        logger.info(
            "[action_extractor] leads_to=%d syntactic=%d shared_entity=%d keyword=%d shared_subject=%d obj_obj=%d",
            len(leads_to_best), len(already_syntactic), len(already_shared), len(already_keyword), len(already_subject), len(already_obj_obj),
        )
        return deps

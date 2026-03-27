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

Link Score (LS):
  - Режим «сильная связность» (causal_density >= DENSE_THRESHOLD):
      regex match против STRONG_MARKERS, threshold >= 0.70
  - Режим «слабая связность» (causal_density < DENSE_THRESHOLD):
      дополнительно: синтаксические связи (xcomp, advcl, ccomp) в одном предложении, LS=0.65
      threshold снижен до 0.60

Детекция слабой связности:
    causal_density = (число сильных маркеров в тексте) / (число предложений)
    DENSE_THRESHOLD = 0.08  (менее 1 маркера на 12 предложений → слабая)
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import List

from action_markers import STRONG_MARKERS

logger = logging.getLogger(__name__)

# Patterns that indicate an action is an artifact (DOI, copyright, table cell, hyphenation, section heading)
_ARTIFACT_PATTERNS = re.compile(
    r'^(?:'
    r'doi:\S+|'                          # DOI strings
    r'Received\s+doi|'                   # "Received doi:..."
    r'See\s+the\s+Terms|'               # copyright notice
    r'http[s]?://|'                      # URLs
    r'\w+-\s*$'                          # hyphenated word at end (line-break artifact)
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

# Pattern: full_phrase starts with capital after verb — likely section heading artifact
# e.g. "governed The hallmarks of..."
_HEADING_ARTIFACT_PAT = re.compile(r'^\w+\s+[A-Z][a-z]')

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
}

# Compiled marker patterns for speed
_COMPILED_MARKERS = [(re.compile(pat, re.IGNORECASE), score) for pat, score in STRONG_MARKERS]

# For density detection: compile all marker patterns into a single fast regex
_ALL_MARKER_PAT = re.compile(
    '|'.join(pat for pat, _ in STRONG_MARKERS),
    re.IGNORECASE,
)

# Causal density threshold: below → sparse/weakly-connected text
DENSE_THRESHOLD = 0.08  # < 1 marker per 12 sentences

# Link score thresholds by mode
LINK_SCORE_THRESHOLD_DENSE = 0.70
LINK_SCORE_THRESHOLD_SPARSE = 0.60
SYNTACTIC_LINK_SCORE = 0.65   # score assigned to syntactic (xcomp/advcl/ccomp) links

# Window (in characters) around an action's position to search for dependency markers
_MARKER_WINDOW = 300   # slightly wider to catch cross-sentence markers


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


@dataclass
class ExtractedDependency:
    source_id: str
    target_id: str
    marker_text: str
    link_score: float


def _get_object_np(token) -> str:
    """Return the object NP text for a verb token, or empty string.

    Tries direct object dependencies first, then falls back to
    xcomp/ccomp for verbs like 'cause', 'lead', 'result'.
    Subtree capped at 12 tokens to avoid grabbing whole clauses.
    """
    # Primary: direct object
    for child in token.children:
        if child.dep_ in ('obj', 'dobj', 'nsubj:pass'):
            subtree = list(child.subtree)
            if len(subtree) > 12:
                # Return just the head + immediate determiners/adjectives
                det = next((c.text for c in child.children if c.dep_ in ('det', 'amod')), '')
                return f"{det} {child.text}".strip() if det else child.text
            return child.doc[subtree[0].i: subtree[-1].i + 1].text

    # Secondary: oblique argument (obl) — common in passive constructions
    for child in token.children:
        if child.dep_ == 'obl':
            subtree = list(child.subtree)
            if len(subtree) > 8:
                return child.text
            return child.doc[subtree[0].i: subtree[-1].i + 1].text

    return ''


def _action_score(token, obj_text: str) -> float:
    """Compute Action Score. Returns 0.0 if no object (hard gate)."""
    if not obj_text:
        return 0.0  # Hard gate: object is mandatory
    has_content_verb = 1.0 if (token.pos_ == 'VERB' and token.lemma_.lower() not in STOP_VERBS) else 0.0
    not_aux = 1.0 if token.pos_ != 'AUX' else 0.0
    has_modifier = 0.0
    for child in token.children:
        if child.dep_ in ('amod', 'advmod'):
            has_modifier = 1.0
            break
    return 0.55 * has_content_verb + 0.30 * not_aux + 0.15 * has_modifier


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


class ActionExtractor:
    """Extracts actions and their dependencies from text using a spaCy model."""

    def extract(self, text: str, nlp) -> tuple[list[ExtractedAction], list[ExtractedDependency]]:
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
                obj_text = _get_object_np(token)
                score = _action_score(token, obj_text)
                if score < 0.55:
                    continue

                modifiers = [
                    child.text for child in token.children
                    if child.dep_ in ('amod', 'advmod', 'neg')
                ]

                full_phrase = f"{token.text} {obj_text}".strip()

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

                # Filter artifacts: DOI, copyright, hyphenation
                if _ARTIFACT_PATTERNS.search(full_phrase):
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
                    char_end=token.idx + len(token.text),
                    modifiers=modifiers,
                    action_score=score,
                ))

        deps = self._extract_dependencies(actions, text, doc, is_sparse, link_threshold)
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
        is_sparse: bool,
        link_threshold: float,
    ) -> list[ExtractedDependency]:
        """Find dependencies between actions.

        Dense mode: regex markers only (threshold 0.70).
        Sparse mode: regex markers (threshold 0.60) + syntactic links within sentence.
        """
        deps: list[ExtractedDependency] = []
        if len(actions) < 2:
            return deps

        # Build lookup: sentence_idx → list of action indices
        sent_to_actions: dict[int, list[int]] = {}
        for i, a in enumerate(actions):
            sent_to_actions.setdefault(a.sentence_idx, []).append(i)

        # ── 1. Marker-based dependencies (consecutive action pairs) ──────────
        for i in range(len(actions) - 1):
            src = actions[i]
            tgt = actions[i + 1]

            gap_start = max(0, src.char_end)
            gap_end = min(len(text), tgt.char_start + _MARKER_WINDOW)
            gap_text = text[gap_start:gap_end]

            best_score = 0.0
            best_marker = ''
            for pattern, score in _COMPILED_MARKERS:
                m = pattern.search(gap_text)
                if m and score > best_score:
                    best_score = score
                    best_marker = m.group(0)

            if best_score >= link_threshold:
                deps.append(ExtractedDependency(
                    source_id=src.action_id,
                    target_id=tgt.action_id,
                    marker_text=best_marker,
                    link_score=best_score,
                ))

        # ── 2. Syntactic dependencies within same sentence (sparse mode) ─────
        if is_sparse:
            # Build token→action_id map for fast lookup
            tok_to_action: dict[int, str] = {}
            for a in actions:
                # Find the verb token by char position
                for tok in doc:
                    if tok.idx == a.char_start:
                        tok_to_action[tok.i] = a.action_id
                        break

            syntactic_rels = {'xcomp', 'advcl', 'ccomp', 'conj'}
            already_linked: set[tuple[str, str]] = {(d.source_id, d.target_id) for d in deps}

            for tok in doc:
                if tok.i not in tok_to_action:
                    continue
                src_id = tok_to_action[tok.i]
                for child in tok.children:
                    if child.dep_ in syntactic_rels and child.i in tok_to_action:
                        tgt_id = tok_to_action[child.i]
                        if src_id != tgt_id and (src_id, tgt_id) not in already_linked:
                            already_linked.add((src_id, tgt_id))
                            deps.append(ExtractedDependency(
                                source_id=src_id,
                                target_id=tgt_id,
                                marker_text=f"[syntactic:{child.dep_}]",
                                link_score=SYNTACTIC_LINK_SCORE,
                            ))

        return deps

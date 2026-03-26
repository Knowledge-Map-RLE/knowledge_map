"""
ActionExtractor — извлечение действий и причинно-следственных связей из текста.

Использует уже загруженную spaCy модель (en_core_sci_scibert).
Action Score (AS):
    0.40 * has_content_verb  (POS=VERB AND lemma not in STOP_VERBS)
    0.35 * has_object        (dep in obj, nsubj:pass, obl)
    0.20 * not_aux           (POS != AUX)
    0.05 * has_modifier      (dep in amod, advmod)
Threshold: AS >= 0.55

Link Score (LS): regex match against STRONG_MARKERS, threshold >= 0.70
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional

from action_markers import STRONG_MARKERS

logger = logging.getLogger(__name__)

STOP_VERBS = {
    'be', 'have', 'do', 'get', 'make', 'seem', 'appear', 'remain',
    'become', 'include', 'involve', 'contain', 'represent', 'constitute',
    'use', 'show', 'find', 'suggest', 'indicate', 'note', 'observe',
    'report', 'describe', 'discuss', 'present', 'provide', 'give',
}

# Compiled marker patterns for speed
_COMPILED_MARKERS = [(re.compile(pat, re.IGNORECASE), score) for pat, score in STRONG_MARKERS]

ACTION_SCORE_THRESHOLD = 0.55
LINK_SCORE_THRESHOLD = 0.70

# Window (in characters) around an action's position to search for dependency markers
_MARKER_WINDOW = 200


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
    """Return the object NP text for a verb token, or empty string."""
    for child in token.children:
        if child.dep_ in ('obj', 'dobj', 'nsubj:pass', 'obl'):
            # Collect the subtree span (limited to avoid grabbing whole clauses)
            subtree_tokens = list(child.subtree)
            # Filter out clause-level subtrees (>8 tokens = too long)
            if len(subtree_tokens) > 8:
                return child.text
            return child.doc[subtree_tokens[0].i: subtree_tokens[-1].i + 1].text
    return ''


def _action_score(token, obj_text: str) -> float:
    """Compute Action Score for a token."""
    has_content_verb = 1.0 if (token.pos_ == 'VERB' and token.lemma_.lower() not in STOP_VERBS) else 0.0
    has_object = 1.0 if obj_text else 0.0
    not_aux = 1.0 if token.pos_ != 'AUX' else 0.0
    has_modifier = 0.0
    for child in token.children:
        if child.dep_ in ('amod', 'advmod'):
            has_modifier = 1.0
            break
    return 0.40 * has_content_verb + 0.35 * has_object + 0.20 * not_aux + 0.05 * has_modifier


class ActionExtractor:
    """Extracts actions and their dependencies from text using a spaCy model."""

    def extract(self, text: str, nlp) -> tuple[list[ExtractedAction], list[ExtractedDependency]]:
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
                if score < ACTION_SCORE_THRESHOLD:
                    continue

                modifiers = [
                    child.text for child in token.children
                    if child.dep_ in ('amod', 'advmod', 'neg')
                ]

                full_phrase = f"{token.text} {obj_text}".strip() if obj_text else token.text

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

        deps = self._extract_dependencies(actions, text)
        logger.debug("[action_extractor] text_len=%d actions=%d deps=%d", len(text), len(actions), len(deps))
        return actions, deps

    def _extract_dependencies(
        self, actions: list[ExtractedAction], text: str
    ) -> list[ExtractedDependency]:
        """Find strong marker patterns between consecutive actions."""
        deps: list[ExtractedDependency] = []
        if len(actions) < 2:
            return deps

        for i in range(len(actions) - 1):
            src = actions[i]
            tgt = actions[i + 1]
            # Оба конца должны иметь объект (score > 0.60) иначе связь бессмысленна
            if not src.object_text or not tgt.object_text:
                continue

            # The text between the two action positions (+ small buffer)
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

            if best_score >= LINK_SCORE_THRESHOLD:
                deps.append(ExtractedDependency(
                    source_id=src.action_id,
                    target_id=tgt.action_id,
                    marker_text=best_marker,
                    link_score=best_score,
                ))

        return deps

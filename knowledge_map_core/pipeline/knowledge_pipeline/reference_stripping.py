"""Deterministic removal of the trailing references section before NLP/LLM.

The references section is bibliography and adds no biological assertions, so the
pipeline strips it from the source text before the NLP and LLM calls. Cutting a
tail keeps every earlier byte offset unchanged, so spans over the stripped text
remain valid. The function is idempotent.
"""
from __future__ import annotations

import re
from typing import Optional


_REFERENCES_HEADING_RE = re.compile(
    r"^\s*(?:#{1,6}\s+)?(?:references|reference list|bibliography|works cited|"
    r"literature cited|references and notes)(?:\s*[\[(].*?[\])])?\s*:?\s*$",
    re.IGNORECASE,
)

_LINE_RE = re.compile(r"(?m)^.*$")


def strip_references(text: str) -> str:
    """Return ``text`` without the trailing references section."""
    stripped, _ = strip_references_info(text)
    return stripped


def strip_references_info(text: str) -> tuple[str, Optional[dict]]:
    """Return ``(stripped_text, removed_info)``.

    ``removed_info`` is ``None`` when no references heading is found, otherwise
    ``{"start_char", "heading", "removed_chars"}`` where offsets are byte/codepoint
    offsets into the input text (matching the pipeline offset encoding).
    """
    text = text or ""
    for match in _LINE_RE.finditer(text):
        line = match.group(0)
        stripped = line.strip()
        if stripped and _REFERENCES_HEADING_RE.match(stripped):
            start = match.start()
            removed = len(text) - start
            return text[:start].rstrip(), {
                "start_char": start,
                "heading": stripped,
                "removed_chars": removed,
            }
    return text, None
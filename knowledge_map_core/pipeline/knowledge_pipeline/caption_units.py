"""Identification of figure and table caption source units.

The extraction pipeline operates on NLP sentences, while a caption is normally
written as one Markdown line.  This module bridges those representations without
changing source offsets: every sentence overlapping a caption line is a caption
source unit and must be accounted for separately.
"""
from __future__ import annotations

import re


_CAPTION_LINE_RE = re.compile(
    r"(?im)^\s*(?:#{1,6}\s*)?(?:supplementary\s+|extended\s+data\s+)?"
    r"(?:figure|fig\.?|table|рис(?:унок|\.)?|таблица)\s*"
    r"(?:[0-9]+|[a-zа-яё]+)\s*[:.\-—]"
)

_HTML_CAPTION_RE = re.compile(
    r"(?is)<figcaption\b[^>]*>.*?(?:figure|fig\.?|table|рис(?:унок|\.)?|таблица)\s*"
    r"(?:[0-9]+|[a-zа-яё]+).*?</figcaption>"
)


def caption_unit_indexes(profile: dict, source_text: str) -> set[int]:
    """Return zero-based sentence indexes that overlap labelled caption lines.

    Labels are intentionally detected in both English and Russian.  A caption
    can contain multiple NLP sentences, all of which remain knowledge-bearing
    source units rather than being discarded as media-only text.
    """
    indexes: set[int] = set()
    matches = list(_CAPTION_LINE_RE.finditer(source_text)) + list(_HTML_CAPTION_RE.finditer(source_text))
    for match in matches:
        line_end = source_text.find("\n", match.start())
        caption_end = match.end() if match.re is _HTML_CAPTION_RE else (
            len(source_text) if line_end == -1 else line_end)
        for index, sentence in enumerate(profile.get("sentences", [])):
            if sentence["start"] < caption_end and sentence["end"] > match.start():
                indexes.add(index)
    return indexes


def caption_unit_ids(profile: dict, source_text: str) -> set[str]:
    return {f"S{index + 1}" for index in caption_unit_indexes(profile, source_text)}

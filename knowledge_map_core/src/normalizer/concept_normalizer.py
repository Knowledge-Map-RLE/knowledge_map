from __future__ import annotations

import re

from src.domain.interfaces import ConceptNormalizer


class ConceptNormalizerImpl(ConceptNormalizer):
    def normalize(self, text: str) -> str:
        text = text.strip()
        text = re.sub(r"\s+", " ", text)
        text = text.lower()
        text = re.sub(r"^(a|an|the)\s+", "", text)
        text = self._singularize(text)
        return text

    def _singularize(self, word: str) -> str:
        if word.endswith("ies") and len(word) > 4:
            return word[:-3] + "y"
        if word.endswith("ses") and len(word) > 4:
            return word[:-2]
        if word.endswith("xes") and len(word) > 4:
            return word[:-2]
        if word.endswith("s") and not word.endswith("ss") and len(word) > 3:
            return word[:-1]
        return word

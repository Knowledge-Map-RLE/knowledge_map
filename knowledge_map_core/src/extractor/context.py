from __future__ import annotations

from dataclasses import dataclass, field

from src.domain.models import Statement, Concept


@dataclass
class ExtractionContext:
    sentence_text: str
    existing_concepts: dict[str, Concept] = field(default_factory=dict)
    existing_statements: list[Statement] = field(default_factory=list)
    doc_id: str = ""

    def get_or_create_concept(self, text: str) -> Concept:
        key = text.lower().strip()
        if key in self.existing_concepts:
            return self.existing_concepts[key]
        concept = Concept(
            id=f"concept_{len(self.existing_concepts)}",
            text=text.strip(),
        )
        self.existing_concepts[key] = concept
        return concept

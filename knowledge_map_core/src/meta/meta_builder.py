from __future__ import annotations

from src.domain.models import Statement, StatementType, StatementID, Concept
from src.domain.interfaces import PipelineStep


class MetaBuilder(PipelineStep):
    """Builds meta-statements (M-type) linking facts discovered from context."""

    def process(
        self,
        statements: list[Statement],
        concepts: dict[str, Concept],
        context: dict,
    ) -> tuple[list[Statement], dict[str, Concept]]:
        facts = [s for s in statements if s.type == StatementType.FACT]
        meta_statements: list[Statement] = []

        for i, fact_a in enumerate(facts):
            for fact_b in facts[i + 1:]:
                shared = self._find_shared_concept(fact_a, fact_b)
                if shared:
                    meta = Statement(
                        id=StatementID.new(),
                        type=StatementType.META,
                        subject=fact_a,
                        predicate="related_to",
                        object=fact_b,
                        sentence_text=context.get("sentence", ""),
                        metadata={"via_concept": shared},
                    )
                    meta_statements.append(meta)

        statements.extend(meta_statements)
        return statements, concepts

    @staticmethod
    def _find_shared_concept(a: Statement, b: Statement) -> str | None:
        subjects_objects_a = {a.subject_id, a.object_id}
        subjects_objects_b = {b.subject_id, b.object_id}
        shared = subjects_objects_a & subjects_objects_b
        return next(iter(shared)) if shared else None

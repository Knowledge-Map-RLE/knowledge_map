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
        if len(facts) < 2:
            return statements, concepts

        meta_statements: list[Statement] = []

        concept_to_facts: dict[str, list[int]] = {}
        for i, fact in enumerate(facts):
            for cid in (fact.subject_id, fact.object_id):
                concept_to_facts.setdefault(cid, []).append(i)

        seen_pairs: set[tuple[int, int]] = set()
        for cid, fact_idxs in concept_to_facts.items():
            if len(fact_idxs) < 2:
                continue
            for i in range(len(fact_idxs)):
                for j in range(i + 1, len(fact_idxs)):
                    a_idx, b_idx = fact_idxs[i], fact_idxs[j]
                    pair = (a_idx, b_idx) if a_idx < b_idx else (b_idx, a_idx)
                    if pair in seen_pairs:
                        continue
                    seen_pairs.add(pair)
                    fact_a = facts[a_idx]
                    fact_b = facts[b_idx]
                    meta = Statement(
                        id=StatementID.new(),
                        type=StatementType.META,
                        subject=fact_a,
                        predicate="related_to",
                        object=fact_b,
                        sentence_text=context.get("sentence", ""),
                        metadata={"via_concept": cid},
                    )
                    meta_statements.append(meta)

        statements.extend(meta_statements)
        return statements, concepts

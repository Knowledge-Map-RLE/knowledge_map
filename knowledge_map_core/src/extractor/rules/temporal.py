from __future__ import annotations

from src.domain.models import Statement, StatementType, StatementID
from src.extractor.context import ExtractionContext
from src.extractor.rules.base import BaseRule
from src.parser.dep_tree import DependencyTree


class TemporalRule(BaseRule):
    """X before Y (temporal relation)

    Matches: advcl with temporal markers, obl:tmod, nmod:tmod
    Examples:
      - Since the discovery of dopamine in the 1950s...
      - After the identification of the first gene...
      - PD research before 2000 focused on dopamine.
    """

    TEMPORAL_MARKERS = {"since", "before", "after", "during", "until", "when", "while", "throughout", "following"}

    @property
    def name(self) -> str:
        return "temporal"

    def matches(self, tree: DependencyTree) -> bool:
        for tok in tree.tokens:
            if tok.dep == "advcl":
                markers = [t for t in tree.children(tok.idx) if t.dep == "mark"]
                for m in markers:
                    if m.lemma.lower() in self.TEMPORAL_MARKERS:
                        return True

        for tok in tree.tokens:
            if tok.dep in ("obl:tmod", "nmod:tmod", "obl"):
                if tok.lemma.lower() in self.TEMPORAL_MARKERS:
                    return True

        return False

    def extract(self, tree: DependencyTree, ctx: ExtractionContext) -> list[Statement]:
        statements: list[Statement] = []

        time_expressions = []
        for tok in tree.tokens:
            marker = ""
            if tok.dep == "advcl":
                markers = [t for t in tree.children(tok.idx) if t.dep == "mark"]
                if markers and markers[0].lemma.lower() in self.TEMPORAL_MARKERS:
                    marker = markers[0].lemma.lower()
                    time_text = tree.subtree_text(tok.idx)
                    if time_text:
                        time_expressions.append((marker, time_text, tok.idx))

            if tok.dep in ("obl:tmod", "nmod:tmod"):
                time_text = tree.subtree_text(tok.idx)
                if time_text:
                    time_expressions.append(("at", time_text, tok.idx))

            if tok.dep == "obl" and tok.dep != "obl:tmod":
                prep_children = [t for t in tree.children(tok.idx)]
                for child in prep_children:
                    lemmas = set(t.lemma.lower() for t in [child] + tree.children(child.idx))
                    if lemmas & self.TEMPORAL_MARKERS | {tok.lemma.lower()}:
                        if lemmas & self.TEMPORAL_MARKERS:
                            matched_markers = lemmas & self.TEMPORAL_MARKERS
                            marker = next(iter(matched_markers))
                            time_text = tree.subtree_text(tok.idx)
                            if time_text:
                                time_expressions.append((marker, time_text, tok.idx))

        for marker, time_text, time_token_idx in time_expressions:
            main_event_tokens = [t for t in tree.tokens if t.dep == "ROOT"]
            if main_event_tokens:
                root = main_event_tokens[0]
                event_text = tree.subtree_text(root.idx)
                if event_text:
                    event_concept = ctx.get_or_create_concept(event_text)
                    time_concept = ctx.get_or_create_concept(time_text)

                    statement = Statement(
                        id=StatementID.new(),
                        type=StatementType.FACT,
                        subject=time_concept,
                        predicate=marker,
                        object=event_concept,
                        sentence_text=ctx.sentence_text,
                        metadata={"temporal": marker},
                    )
                    statements.append(statement)

        return statements

from __future__ import annotations

from src.domain.models import Statement, StatementType, StatementID
from src.extractor.context import ExtractionContext
from src.extractor.rules.base import BaseRule
from src.parser.dep_tree import DependencyTree


class TemporalComparisonRule(BaseRule):
    """X increases when Y increases → X → increase when → Y

    Handles main verb + advcl with when-advmod temporal comparison.
    Examples:
      - level of DJ-1 increases when cellular levels of ROS increase
        → level of DJ-1 → increase when → cellular levels of ROS increase
    """

    @property
    def name(self) -> str:
        return "temporal_comparison"

    def matches(self, tree: DependencyTree) -> bool:
        for verb in tree.find_by_pos("VERB"):
            if verb.dep != "ROOT":
                continue
            for child in tree.children(verb.idx):
                if child.dep == "advcl" and child.is_verb:
                    for cc in tree.children(child.idx):
                        if cc.dep == "advmod" and cc.lemma == "when":
                            return True
        return False

    def extract(self, tree: DependencyTree, ctx: ExtractionContext) -> list[Statement]:
        statements: list[Statement] = []

        for verb in tree.find_by_pos("VERB"):
            if verb.dep != "ROOT":
                continue

            nsubj_tokens = [c for c in tree.children(verb.idx) if c.dep in ("nsubj", "nsubj:outer")]
            if not nsubj_tokens:
                continue

            subject_text = tree.subtree_text(nsubj_tokens[0].idx)
            if not subject_text:
                continue

            for child in tree.children(verb.idx):
                if child.dep != "advcl" or not child.is_verb:
                    continue

                has_when = any(c.dep == "advmod" and c.lemma == "when" for c in tree.children(child.idx))
                if not has_when:
                    continue

                obj_text = tree.subtree_text(child.idx)
                if not obj_text:
                    continue

                subject = ctx.get_or_create_concept(subject_text)
                obj = ctx.get_or_create_concept(obj_text)
                predicate = f"{verb.lemma} when"

                statement = Statement(
                    id=StatementID.new(),
                    type=StatementType.FACT,
                    subject=subject,
                    predicate=predicate,
                    object=obj,
                    sentence_text=ctx.sentence_text,
                )
                statements.append(statement)

        return statements

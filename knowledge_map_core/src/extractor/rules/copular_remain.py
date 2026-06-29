from __future__ import annotations

from src.domain.models import Statement, StatementType, StatementID
from src.extractor.context import ExtractionContext
from src.extractor.rules.base import BaseRule
from src.parser.dep_tree import DependencyTree


COPULAR_REMAIN = frozenset({"remain", "stay", "become", "seem", "appear"})


class CopularRemainRule(BaseRule):
    """X remains Y → X → remain → Y

    Handles copular-like verbs where the complement is xcomp (adjective or noun).
    The predicate preserves the verb (remain, stay, become, etc).
    Examples:
      - The role remains elusive → role → remain → elusive
    """

    @property
    def name(self) -> str:
        return "copular_remain"

    def matches(self, tree: DependencyTree) -> bool:
        for verb in tree.find_by_pos("VERB"):
            if verb.lemma in COPULAR_REMAIN:
                has_nsubj = any(c.dep in ("nsubj", "nsubj:outer") for c in tree.children(verb.idx))
                has_xcomp = any(c.dep == "xcomp" for c in tree.children(verb.idx))
                if has_nsubj and has_xcomp:
                    return True
        return False

    def extract(self, tree: DependencyTree, ctx: ExtractionContext) -> list[Statement]:
        statements: list[Statement] = []

        for verb in tree.find_by_pos("VERB"):
            if verb.lemma not in COPULAR_REMAIN:
                continue

            nsubj_tokens = [c for c in tree.children(verb.idx) if c.dep in ("nsubj", "nsubj:outer")]
            if not nsubj_tokens:
                continue

            xcomp_tokens = [c for c in tree.children(verb.idx) if c.dep == "xcomp"]
            if not xcomp_tokens:
                continue

            subject_text = tree.subtree_text(nsubj_tokens[0].idx)
            if not subject_text:
                continue
            subject = ctx.get_or_create_concept(subject_text)

            for xc in xcomp_tokens:
                obj_text = tree.subtree_text(xc.idx)
                if not obj_text:
                    continue
                obj = ctx.get_or_create_concept(obj_text)

                statement = Statement(
                    id=StatementID.new(),
                    type=StatementType.FACT,
                    subject=subject,
                    predicate=verb.lemma,
                    object=obj,
                    sentence_text=ctx.sentence_text,
                )
                statements.append(statement)

        return statements

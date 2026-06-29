from __future__ import annotations

from src.domain.models import Statement, StatementType, StatementID
from src.extractor.context import ExtractionContext
from src.extractor.rules.base import BaseRule
from src.parser.dep_tree import DependencyTree


class RelativeClauseRule(BaseRule):
    """X, which is Y → X → is → Y

    Matches: relcl (relative clause)
    Examples:
      - PD, which is age-related, ...
      - The study, which revealed complexity, ...
      - Factors that influence PD ...
    """

    @property
    def name(self) -> str:
        return "relative_clause"

    def matches(self, tree: DependencyTree) -> bool:
        relcl = tree.find_by_dep("relcl")
        return len(relcl) > 0

    def extract(self, tree: DependencyTree, ctx: ExtractionContext) -> list[Statement]:
        statements: list[Statement] = []

        for relcl_token in tree.find_by_dep("relcl"):
            head = tree.token_by_idx(relcl_token.head_idx)
            if not head:
                continue

            head_text = tree.subtree_text(head.idx)
            if not head_text:
                continue
            subject = ctx.get_or_create_concept(head_text)

            nsubj_children = [t for t in tree.children(relcl_token.idx) if t.dep == "nsubj"]
            if nsubj_children:
                actual_subj_text = tree.subtree_text(nsubj_children[0].idx)
                if actual_subj_text:
                    subject = ctx.get_or_create_concept(actual_subj_text)

            cop = [t for t in tree.children(relcl_token.idx) if t.dep == "cop"]
            if cop:
                pred_lemma = cop[0].lemma
                attrs = [t for t in tree.children(relcl_token.idx) if t.dep in ("attr", "adj", "amod", "acomp")]
                for attr in attrs:
                    attr_text = tree.subtree_text(attr.idx)
                    if not attr_text:
                        continue
                    obj = ctx.get_or_create_concept(attr_text)
                    statement = Statement(
                        id=StatementID.new(),
                        type=StatementType.FACT,
                        subject=subject,
                        predicate=pred_lemma,
                        object=obj,
                        sentence_text=ctx.sentence_text,
                    )
                    statements.append(statement)

            obj_children = [t for t in tree.children(relcl_token.idx) if t.dep in ("obj", "dobj")]
            if obj_children and not cop:
                verb_text = relcl_token.lemma
                for obj in obj_children:
                    obj_text = tree.subtree_text(obj.idx)
                    if not obj_text:
                        continue
                    obj_concept = ctx.get_or_create_concept(obj_text)
                    statement = Statement(
                        id=StatementID.new(),
                        type=StatementType.FACT,
                        subject=subject,
                        predicate=verb_text,
                        object=obj_concept,
                        sentence_text=ctx.sentence_text,
                    )
                    statements.append(statement)

        return statements

from __future__ import annotations

import logging

from src.domain.models import Statement, StatementType, StatementID
from src.extractor.context import ExtractionContext
from src.extractor.rules.base import BaseRule
from src.parser.dep_tree import DependencyTree

logger = logging.getLogger(__name__)


class CoordinationRule(BaseRule):
    """Splits coordinated elements into separate statements.

    Pattern: A and B (conj + cc)
    Cases:
      - ADJ and ADJ modifying same noun → noun → property → adj (×2)
      - NOUN and NOUN → each noun gets separate statement with shared context
    """

    @property
    def name(self) -> str:
        return "coordination"

    def matches(self, tree: DependencyTree) -> bool:
        return len(tree.find_by_dep("conj")) > 0 and len(tree.find_by_dep("cc")) > 0

    def _shared_parent_text(self, tree: DependencyTree, head_idx: int, conj_idxs: set[int]) -> str:
        """Get parent text excluding the coordinated nodes."""
        parent = tree.token_by_idx(head_idx)
        if not parent:
            return ""
        tokens = [parent]
        for child in tree.children(head_idx):
            if child.idx in conj_idxs:
                continue
            for t in tree.subtree_tokens(child.idx):
                if t.idx not in conj_idxs:
                    tokens.append(t)
        tokens.sort(key=lambda t: t.idx)
        return " ".join(t.text for t in tokens if not t.is_punct and not t.is_space)

    def extract(self, tree: DependencyTree, ctx: ExtractionContext) -> list[Statement]:
        statements: list[Statement] = []

        for conj_token in tree.find_by_dep("conj"):
            head = tree.token_by_idx(conj_token.head_idx)
            if not head:
                continue

            head_text = tree.subtree_text(head.idx)
            conj_text = tree.subtree_text(conj_token.idx)
            if not head_text or not conj_text:
                continue

            is_adjective = conj_token.is_adj or head.is_adj
            if not is_adjective:
                continue

            shared_parent_idx = head.head_idx if head.dep != "ROOT" else None

            if shared_parent_idx is not None:
                conj_idxs = {head.idx, conj_token.idx}
                shared_text = self._shared_parent_text(tree, shared_parent_idx, conj_idxs)
                if not shared_text:
                    continue
                shared = ctx.get_or_create_concept(shared_text)

                stmt1 = Statement(
                    id=StatementID.new(),
                    type=StatementType.FACT,
                    subject=shared,
                    predicate="property",
                    object=ctx.get_or_create_concept(head_text),
                    sentence_text=ctx.sentence_text,
                )
                statements.append(stmt1)

                stmt2 = Statement(
                    id=StatementID.new(),
                    type=StatementType.FACT,
                    subject=shared,
                    predicate="property",
                    object=ctx.get_or_create_concept(conj_text),
                    sentence_text=ctx.sentence_text,
                )
                statements.append(stmt2)
            else:
                stmt_conj = Statement(
                    id=StatementID.new(),
                    type=StatementType.FACT,
                    subject=ctx.get_or_create_concept(head_text),
                    predicate="and",
                    object=ctx.get_or_create_concept(conj_text),
                    sentence_text=ctx.sentence_text,
                )
                statements.append(stmt_conj)

        return statements

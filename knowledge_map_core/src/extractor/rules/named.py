from __future__ import annotations

from src.domain.models import Statement, StatementType, StatementID
from src.extractor.context import ExtractionContext
from src.extractor.rules.base import BaseRule
from src.parser.dep_tree import DependencyTree, TokenInfo


NAMED_VERBS = {"name", "call", "term", "designate"}


class NamedRule(BaseRule):
    """X named Y → X → be → Y

    Matches acl verbs like named/called/termed that rename/modify a head noun.
    Examples:
      - an atypical form of PD with dementia, named Kufor-Rakeb syndrome
        → atypical form of PD with dementia → be → Kufor-Rakeb syndrome
    """

    @property
    def name(self) -> str:
        return "named"

    def matches(self, tree: DependencyTree) -> bool:
        for t in tree.tokens:
            if t.dep == "acl" and t.lemma in NAMED_VERBS:
                has_xcomp = any(c.dep == "xcomp" for c in tree.children(t.idx))
                if has_xcomp:
                    return True
        return False

    def _head_subject_text(self, head: TokenInfo, tree: DependencyTree) -> str:
        """Build subject text from head noun, excluding acl and citation children."""
        tokens: list[TokenInfo] = [head]
        excluded_deps = {"acl", "acl:relcl", "relcl", "punct", "appos", "dep", "nummod"}
        for c in tree.children(head.idx):
            if c.dep in excluded_deps:
                continue
            tokens.extend(tree.subtree_tokens(c.idx))
        tokens.sort(key=lambda t: t.idx)
        parts = [t.text for t in tokens if not t.is_punct and not t.is_space]
        return " ".join(parts) if parts else ""

    def extract(self, tree: DependencyTree, ctx: ExtractionContext) -> list[Statement]:
        statements: list[Statement] = []

        for t in tree.tokens:
            if t.dep != "acl" or t.lemma not in NAMED_VERBS:
                continue

            head = tree.token_by_idx(t.head_idx)
            if not head:
                continue

            subject_text = self._head_subject_text(head, tree)
            if not subject_text:
                continue
            subject = ctx.get_or_create_concept(subject_text)

            for c in tree.children(t.idx):
                if c.dep == "xcomp":
                    obj_text = tree.subtree_text(c.idx)
                    if not obj_text:
                        continue
                    obj = ctx.get_or_create_concept(obj_text)
                    statement = Statement(
                        id=StatementID.new(),
                        type=StatementType.FACT,
                        subject=subject,
                        predicate="be",
                        object=obj,
                        sentence_text=ctx.sentence_text,
                    )
                    statements.append(statement)

        return statements

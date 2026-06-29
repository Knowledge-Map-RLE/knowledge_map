from __future__ import annotations

from src.domain.models import Statement, StatementType, StatementID
from src.extractor.context import ExtractionContext
from src.extractor.rules.base import BaseRule
from src.parser.dep_tree import DependencyTree


class SuchAsRule(BaseRule):
    """X such as Y → X → include → Y

    Handles both ``X, such as Y`` and ``X including Y``.
    Examples:
      - nonmotor symptoms, such as hyposmia, depression, ...
      - population-based studies, including genome-wide association studies
    """

    @property
    def name(self) -> str:
        return "such_as"

    def _is_such_as(self, tree: DependencyTree, token_idx: int) -> bool:
        """Check if token is the head of 'such as' phrase."""
        tok = tree.token_by_idx(token_idx)
        if not tok or tok.lemma != "such" or tok.dep != "case":
            return False
        for c in tree.children(token_idx):
            if c.lemma == "as" and c.dep == "mwe":
                return True
        return False

    def _is_including(self, tree: DependencyTree, token_idx: int) -> bool:
        """Check if token is 'including' as a preposition-like case."""
        tok = tree.token_by_idx(token_idx)
        if not tok:
            return False
        return tok.lemma == "include" and tok.dep == "case"

    def _collect_conjuncts(self, tree: DependencyTree, head_idx: int) -> list[int]:
        seen: set[int] = set()
        result: list[int] = []

        def _walk(idx: int) -> None:
            if idx in seen:
                return
            seen.add(idx)
            result.append(idx)
            for child in tree.children(idx):
                if child.dep == "conj":
                    _walk(child.idx)

        _walk(head_idx)
        return result

    def _resolve_example_subject(self, example_head_idx: int, tree: DependencyTree) -> str | None:
        """Walk up from the example through nmod/relcl chain to find the semantic subject.

        Skips the example itself — always walks to at least the nmod's head.
        Only returns when a noun's head is NOT a relcl verb (terminal antecedent).
        """
        ex_head = tree.token_by_idx(example_head_idx)
        if not ex_head:
            return None

        stack = [ex_head.head_idx]
        visited: set[int] = set()

        while stack:
            idx = stack.pop()
            if idx in visited:
                continue
            visited.add(idx)

            tok = tree.token_by_idx(idx)
            if not tok:
                continue

            if tok.is_verb and tok.dep in ("acl:relcl", "relcl"):
                stack.append(tok.head_idx)
                continue

            if tok.is_noun or tok.is_adj:
                parent = tree.token_by_idx(tok.head_idx)
                if parent and parent.is_verb and parent.dep in ("acl:relcl", "relcl"):
                    stack.append(parent.idx)
                    continue

                ant_nsubj = [t for t in tree.children(idx) if t.dep in ("nsubj", "nsubjpass")]
                if ant_nsubj:
                    resolved = tree.subtree_text(ant_nsubj[0].idx)
                    if resolved:
                        return resolved

                tokens = [tok]
                for child in tree.children(idx):
                    if child.dep in ("det", "amod", "compound", "nmod:poss", "nummod"):
                        tokens.extend(tree.subtree_tokens(child.idx))
                tokens.sort(key=lambda t: t.idx)
                text = " ".join(t.text for t in tokens if not t.is_punct and not t.is_space)
                if text:
                    return text

                if parent and parent.is_noun:
                    stack.append(parent.idx)

        return None

    def matches(self, tree: DependencyTree) -> bool:
        for t in tree.tokens:
            if self._is_such_as(tree, t.idx) or self._is_including(tree, t.idx):
                return True
        return False

    def extract(self, tree: DependencyTree, ctx: ExtractionContext) -> list[Statement]:
        statements: list[Statement] = []

        for t in tree.tokens:
            if not (self._is_such_as(tree, t.idx) or self._is_including(tree, t.idx)):
                continue

            # The nmod (head of such/including)
            example_head = tree.token_by_idx(t.head_idx)
            if not example_head:
                continue

            examples = self._collect_conjuncts(tree, example_head.idx)
            if not examples:
                continue

            # Resolve subject by walking up from the example's head
            subject_text = self._resolve_example_subject(example_head.idx, tree)
            if not subject_text:
                continue

            subject = ctx.get_or_create_concept(subject_text)

            for ex_idx in examples:
                ex = tree.token_by_idx(ex_idx)
                if not ex:
                    continue

                # Build example text: head + premodifiers
                tokens = [ex]
                for child in tree.children(ex_idx):
                    if child.dep in ("det", "amod", "compound", "nmod:poss", "nummod"):
                        tokens.extend(tree.subtree_tokens(child.idx))
                tokens.sort(key=lambda t: t.idx)
                obj_text = " ".join(t.text for t in tokens if not t.is_punct and not t.is_space)
                if not obj_text:
                    continue

                obj = ctx.get_or_create_concept(obj_text)

                statement = Statement(
                    id=StatementID.new(),
                    type=StatementType.FACT,
                    subject=subject,
                    predicate="include",
                    object=obj,
                    sentence_text=ctx.sentence_text,
                )
                statements.append(statement)

        return statements

from __future__ import annotations

from src.domain.models import Statement, StatementType, StatementID
from src.extractor.context import ExtractionContext
from src.extractor.rules.base import BaseRule
from src.parser.dep_tree import DependencyTree


class CopularRule(BaseRule):
    """X is Y → X → is → Y

    UD pattern: ROOT=complement (ADJ/NOUN), nsubj=X, cop=Y
    Examples:
      - Dopamine is a neurotransmitter.
      - PD is age-related.
      - The disease is multifactorial.
    """

    EXCLUDED_DEPS = {"nsubj", "nsubj:outer", "nsubjpass", "nsubj:pass", "cop", "aux", "aux:pass", "auxpass", "mark", "acl", "relcl", "advcl", "ccomp", "xcomp"}

    @property
    def name(self) -> str:
        return "copular"

    def matches(self, tree: DependencyTree) -> bool:
        return len(tree.find_by_dep("cop")) > 0

    def _object_text(self, tree: DependencyTree, complement_idx: int) -> str:
        complement = tree.token_by_idx(complement_idx)
        if not complement:
            return ""
        tokens = [complement]
        for child in tree.children(complement_idx):
            if child.dep in self.EXCLUDED_DEPS:
                continue
            tokens.extend(tree.subtree_tokens(child.idx))
        tokens.sort(key=lambda t: t.idx)
        return " ".join(t.text for t in tokens if not t.is_punct and not t.is_space)

    def extract(self, tree: DependencyTree, ctx: ExtractionContext) -> list[Statement]:
        statements: list[Statement] = []

        for cop_token in tree.find_by_dep("cop"):
            complement = tree.token_by_idx(cop_token.head_idx)
            if not complement:
                continue

            nsubj_tokens = [t for t in tree.children(complement.idx) if t.dep in ("nsubj", "nsubj:outer", "nsubjpass")]
            if not nsubj_tokens:
                # Try xcomp chain: complement's head verb may carry the subject
                comp_head = tree.token_by_idx(complement.head_idx)
                if comp_head and comp_head.is_verb:
                    nsubj_tokens = [t for t in tree.children(complement.head_idx)
                                    if t.dep in ("nsubj", "nsubj:outer", "nsubjpass")]
            if not nsubj_tokens:
                continue

            predicate = cop_token.lemma

            for nsubj in nsubj_tokens:
                subject_text = tree.subtree_text(nsubj.idx)
                if not subject_text:
                    continue
                subject = ctx.get_or_create_concept(subject_text)

                object_text = self._object_text(tree, complement.idx)
                if not object_text:
                    continue
                obj = ctx.get_or_create_concept(object_text)

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

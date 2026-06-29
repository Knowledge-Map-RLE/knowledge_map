from __future__ import annotations

import logging

from src.domain.models import Statement, StatementType, StatementID

logger = logging.getLogger(__name__)
from src.extractor.context import ExtractionContext
from src.extractor.rules.base import BaseRule
from src.parser.dep_tree import DependencyTree


class AsRoleRule(BaseRule):
    """X as Y → X → be → Y

    Pattern: noun_phrase of X as Y / verb X as Y
    Examples:
      - discovery of dopamine as a neurotransmitter
      - revealing PD as an age-related disease
      - PD presents as a Mendelian form
    """

    @property
    def name(self) -> str:
        return "as_role"

    def matches(self, tree: DependencyTree) -> bool:
        for t in tree.tokens:
            if t.lemma == "as" and t.dep in ("case", "mark"):
                return True
        return False

    def _text_without_case(self, tree: DependencyTree, head_idx: int) -> str:
        head = tree.token_by_idx(head_idx)
        if not head:
            return ""
        tokens = [head]
        for child in tree.children(head_idx):
            if child.dep == "case":
                continue
            tokens.extend(tree.subtree_tokens(child.idx))
        tokens.sort(key=lambda t: t.idx)
        return " ".join(t.text for t in tokens if not t.is_punct and not t.is_space)

    def extract(self, tree: DependencyTree, ctx: ExtractionContext) -> list[Statement]:
        statements: list[Statement] = []

        for as_tok in tree.tokens:
            if not (as_tok.lemma == "as" and as_tok.dep in ("case", "mark")):
                continue

            obj_text = ""
            main_head = None

            if as_tok.dep == "case":
                # "as" is a preposition: complement is the parent
                complement = tree.token_by_idx(as_tok.head_idx)
                if complement:
                    obj_text = self._text_without_case(tree, complement.idx)
                    main_head = tree.token_by_idx(complement.head_idx)
            elif as_tok.dep == "mark":
                # "as" is a marker: main head is the parent, complement is a sibling
                main_head = tree.token_by_idx(as_tok.head_idx)
                if main_head:
                    for sib in tree.children(main_head.idx):
                        if sib.idx == as_tok.idx:
                            continue
                        if sib.dep in ("xcomp", "acomp", "nmod", "obl", "ccomp", "advcl"):
                            obj_text = self._text_without_case(tree, sib.idx)
                            break

            if not obj_text or not main_head:
                continue

            subject_text = ""

            # Verb pattern: find obj/dobj
            for sib in tree.children(main_head.idx):
                if sib.dep in ("obj", "dobj"):
                    subject_text = tree.subtree_text(sib.idx)
                    break

            # Noun pattern: find nmod with case "of"
            if not subject_text:
                for sib in tree.children(main_head.idx):
                    if sib.dep == "nmod":
                        for cc in tree.children(sib.idx):
                            if cc.dep == "case" and cc.lemma in ("of",):
                                subject_text = self._text_without_case(tree, sib.idx)
                                break

            # nsubj pattern
            if not subject_text:
                for sib in tree.children(main_head.idx):
                    if sib.dep in ("nsubj",):
                        subject_text = tree.subtree_text(sib.idx)
                        break

            if not subject_text:
                continue

            subject = ctx.get_or_create_concept(subject_text)
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

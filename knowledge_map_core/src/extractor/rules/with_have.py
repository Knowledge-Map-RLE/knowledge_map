from __future__ import annotations

from src.domain.models import Statement, StatementType, StatementID
from src.extractor.context import ExtractionContext
from src.extractor.rules.base import BaseRule
from src.parser.dep_tree import DependencyTree, TokenInfo


class WithHaveRule(BaseRule):
    """X with Y → X → have → Y

    Handles nmod children with case=with on nouns.

    Example: "Mendelian form with autosomal dominant or recessive inheritance"
      → Mendelian form → have → autosomal dominant inheritance
      → Mendelian form → have → autosomal recessive inheritance
    """

    @property
    def name(self) -> str:
        return "with_have"

    def _has_with_case(self, tree: DependencyTree, token: TokenInfo) -> bool:
        return any(
            c.dep in ("nmod", "pobj") and any(
                cc.dep == "case" and cc.lemma == "with"
                for cc in tree.children(c.idx)
            )
            for c in tree.children(token.idx)
        )

    def matches(self, tree: DependencyTree) -> bool:
        for tok in tree.tokens:
            if tok.is_noun and self._has_with_case(tree, tok):
                return True
        return False

    def _split_objects_by_conj(self, tree: DependencyTree, head: TokenInfo) -> list[str]:
        """Split object head + modifiers into separate texts by conjunction.

        For 'autosomal dominant or recessive inheritance' → ['autosomal dominant inheritance', 'recessive inheritance']
        For 'dopamine' (no conj) → ['dopamine']
        For 'hyposmia, depression, constipation' → ['hyposmia', 'depression', 'constipation']
        """
        # Check if head has any noun/adj conj children
        conj_children = [
            c for c in tree.children(head.idx)
            if c.dep == "conj" and (c.is_noun or c.is_adj)
        ]
        if conj_children:
            # Each conj child becomes its own object, with head's shared modifiers
            shared_mods = []
            for child in tree.children(head.idx):
                if child.dep in ("amod", "compound", "det", "nummod", "advmod"):
                    if child.idx < head.idx:
                        shared_mods.append(child)
            results = []
            # First head (without conj)
            head_mods = []
            for child in tree.children(head.idx):
                if child.dep in ("amod", "compound", "det", "nummod", "advmod"):
                    if not any(c.idx == child.idx for c in conj_children):
                        head_mods.append(child)
            tokens = [head] + head_mods
            tokens.sort(key=lambda t: t.idx)
            results.append(" ".join(t.text for t in tokens if not t.is_punct and not t.is_space))
            for cc in conj_children:
                cc_tokens = [head] + [cc] + shared_mods
                cc_tokens.sort(key=lambda t: t.idx)
                results.append(" ".join(t.text for t in cc_tokens if not t.is_punct and not t.is_space))
            return results

        # Check if any amod child has conj children (e.g., dominant or recessive)
        for child in tree.children(head.idx):
            if child.dep in ("amod", "compound") and not child.is_noun:
                conj_of_child = [c for c in tree.children(child.idx) if c.dep == "conj"]
                if conj_of_child:
                    # Amod has conj: split by conjunct
                    pre_mods = []
                    for gc in tree.children(child.idx):
                        if gc.dep in ("amod", "compound", "advmod"):
                            pre_mods.append(gc)
                    results = []
                    # First branch
                    first_text = " ".join(
                        t.text for t in sorted(pre_mods + [child, head], key=lambda t: t.idx)
                        if not t.is_punct and not t.is_space
                    )
                    results.append(first_text)
                    for cc in conj_of_child:
                        conj_text = " ".join(
                            t.text for t in sorted(pre_mods + [cc, head], key=lambda t: t.idx)
                            if not t.is_punct and not t.is_space
                        )
                        results.append(conj_text)
                    return results

        # No conj: return full subtree as single text
        tokens = [head]
        for child in tree.children(head.idx):
            if child.dep in ("amod", "compound", "det", "nummod", "advmod"):
                tokens.extend(tree.subtree_tokens(child.idx))
        tokens.sort(key=lambda t: t.idx)
        return [" ".join(t.text for t in tokens if not t.is_punct and not t.is_space)]

    def _object_text(self, tree: DependencyTree, head: TokenInfo) -> str:
        tokens = [head]
        for child in tree.children(head.idx):
            if child.dep in ("amod", "compound", "det", "nummod", "advmod"):
                tokens.extend(tree.subtree_tokens(child.idx))
        tokens.sort(key=lambda t: t.idx)
        return " ".join(t.text for t in tokens if not t.is_punct and not t.is_space)

    def extract(self, tree: DependencyTree, ctx: ExtractionContext) -> list[Statement]:
        statements: list[Statement] = []

        for tok in tree.tokens:
            if not tok.is_noun:
                continue

            with_nmods = [
                c for c in tree.children(tok.idx)
                if c.dep in ("nmod", "pobj") and any(
                    cc.dep == "case" and cc.lemma == "with"
                    for cc in tree.children(c.idx)
                )
            ]
            if not with_nmods:
                continue

            subject_text = self._object_text(tree, tok)
            if not subject_text:
                continue
            subject = ctx.get_or_create_concept(subject_text)

            for wn in with_nmods:
                object_texts = self._split_objects_by_conj(tree, wn)
                for o_text in object_texts:
                    if not o_text:
                        continue
                    obj = ctx.get_or_create_concept(o_text)
                    statement = Statement(
                        id=StatementID.new(),
                        type=StatementType.FACT,
                        subject=subject,
                        predicate="have",
                        object=obj,
                        sentence_text=ctx.sentence_text,
                    )
                    statements.append(statement)

        return statements

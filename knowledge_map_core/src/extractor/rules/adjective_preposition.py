from __future__ import annotations

from src.domain.models import Statement, StatementType, StatementID
from src.extractor.context import ExtractionContext
from src.extractor.rules.base import BaseRule
from src.parser.dep_tree import DependencyTree


class AdjectivePrepositionRule(BaseRule):
    """X is important for Y → X → be important for → Y

    Handles copular adjectives and progressive verbs followed by advcl/nmod
    with for/in/at. The subject is the nsubj. The object is the advcl/nmod.
    Examples:
      - PINK1 and Parkin are important for maintaining mitochondrial turnover
        → PINK1 → be important for → maintaining mitochondrial turnover
        → Parkin → be important for → maintaining mitochondrial turnover
      - Lewy bodies are lacking in affected carriers
        → Lewy bodies → be lacking in → affected carriers
    """

    ACCEPTED_PREPS = {"for", "in", "at"}

    @property
    def name(self) -> str:
        return "adjective_preposition"

    def _has_prep_child(self, tok, tree: DependencyTree) -> bool:
        for c in tree.children(tok.idx):
            if c.dep in ("advcl", "nmod"):
                for cc in tree.children(c.idx):
                    if cc.dep in ("mark", "case") and cc.lemma in self.ACCEPTED_PREPS:
                        return True
        return False

    def matches(self, tree: DependencyTree) -> bool:
        for tok in tree.tokens:
            if tok.pos == "ADJ" and any(c.dep == "cop" for c in tree.children(tok.idx)):
                if self._has_prep_child(tok, tree):
                    return True
            # Progressive verb: subject + aux(be) + VERBing + nmod(prep)
            if tok.is_verb and any(c.dep == "aux" for c in tree.children(tok.idx)):
                has_nsubj = any(c.dep in ("nsubj", "nsubj:outer") for c in tree.children(tok.idx))
                if has_nsubj and self._has_prep_child(tok, tree):
                    return True
        return False

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

    def _object_text(self, tree: DependencyTree, head_idx: int) -> str:
        """Build object text excluding case prepositions."""
        tokens = [tree.token_by_idx(head_idx)]
        for c in tree.children(head_idx):
            if c.dep in ("case", "mark", "punct", "cc", "dep", "nummod", "appos"):
                continue
            tokens.extend(tree.subtree_tokens(c.idx))
        tokens = [t for t in tokens if t and not t.is_punct and not t.is_space]
        tokens.sort(key=lambda t: t.idx)
        return " ".join(t.text for t in tokens)

    def _handle_prep_child(self, tok, verb_text: str, tree: DependencyTree,
                           nsubj_tokens: list, ctx: ExtractionContext) -> list[Statement]:
        statements: list[Statement] = []
        for prep_child in tree.children(tok.idx):
            if prep_child.dep not in ("advcl", "nmod"):
                continue
            prep_lemmas = [c.lemma for c in tree.children(prep_child.idx) if c.dep in ("mark", "case")]
            matching_prep = next((p for p in prep_lemmas if p in self.ACCEPTED_PREPS), None)
            if not matching_prep:
                continue

            obj_text = self._object_text(tree, prep_child.idx)
            if not obj_text:
                continue
            obj = ctx.get_or_create_concept(obj_text)

            predicate = f"be {verb_text} {matching_prep}"

            subject_idxs = self._collect_conjuncts(tree, nsubj_tokens[0].idx)
            for s_idx in subject_idxs:
                subject_text = tree.subtree_text(s_idx)
                if not subject_text:
                    continue
                subject = ctx.get_or_create_concept(subject_text)

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

    def extract(self, tree: DependencyTree, ctx: ExtractionContext) -> list[Statement]:
        statements: list[Statement] = []

        for tok in tree.tokens:
            nsubj_tokens = [c for c in tree.children(tok.idx) if c.dep in ("nsubj", "nsubj:outer")]
            if not nsubj_tokens:
                continue

            if tok.pos == "ADJ":
                has_cop = any(c.dep == "cop" for c in tree.children(tok.idx))
                if has_cop:
                    statements.extend(self._handle_prep_child(tok, tok.text, tree, nsubj_tokens, ctx))

            # Progressive verb: subject + aux(be) + VERBing + nmod(prep)
            if tok.is_verb and any(c.dep == "aux" for c in tree.children(tok.idx)):
                statements.extend(self._handle_prep_child(tok, tok.text, tree, nsubj_tokens, ctx))

        return statements

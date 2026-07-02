from __future__ import annotations

from src.domain.models import Statement, StatementType, StatementID
from src.extractor.context import ExtractionContext
from src.extractor.rules.base import BaseRule
from src.parser.dep_tree import DependencyTree, TokenInfo


class CopularRule(BaseRule):
    """X is Y → X → is → Y

    UD pattern: ROOT=complement (ADJ/NOUN), nsubj=X, cop=Y
    Examples:
      - Dopamine is a neurotransmitter.
      - PD is age-related.
      - The disease is multifactorial.
    """

    EXCLUDED_DEPS = {"nsubj", "nsubj:outer", "nsubjpass", "nsubj:pass", "cop", "aux", "aux:pass", "auxpass", "mark", "acl", "relcl", "advcl", "ccomp", "xcomp", "neg", "advmod", "discourse", "conj", "cc", "parataxis"}

    DISCOURSE_NOUNS = {"turn", "addition", "contrast", "example", "particular", "conclusion", "summary", "short"}
    SENTENCE_LEVEL_CASE = {"unlike", "like"}

    @property
    def name(self) -> str:
        return "copular"

    def matches(self, tree: DependencyTree) -> bool:
        return len(tree.find_by_dep("cop")) > 0

    def _is_negated(self, tree: DependencyTree, cop_idx: int) -> bool:
        for c in tree.children(cop_idx):
            if c.dep == "neg":
                return True
        cop_token = tree.token_by_idx(cop_idx)
        if cop_token:
            for c in tree.children(cop_token.head_idx):
                if c.dep == "neg":
                    return True
        return False

    def _object_text(self, tree: DependencyTree, complement_idx: int) -> str:
        complement = tree.token_by_idx(complement_idx)
        if not complement:
            return ""
        tokens = [complement]
        for child in tree.children(complement_idx):
            if child.dep in self.EXCLUDED_DEPS:
                continue
            # Skip discourse nmod children (e.g., "in turn", "in addition", "for example")
            if child.lemma in self.DISCOURSE_NOUNS:
                continue
            # Skip nmods with sentence-level case prepositions (e.g., "Unlike cancer")
            if child.dep == "nmod":
                case_tokens = [c for c in tree.children(child.idx) if c.dep == "case"]
                if any(c.lemma in self.SENTENCE_LEVEL_CASE for c in case_tokens):
                    continue
            tokens.extend(tree.subtree_tokens(child.idx))
        tokens.sort(key=lambda t: t.idx)
        return " ".join(t.text for t in tokens if not t.is_punct and not t.is_space)

    def _collect_conjuncts(self, tree: DependencyTree, head_idx: int) -> list[int]:
        """Recursively collect all conjuncts in a coordination chain."""
        seen: set[int] = set()
        result: list[int] = []

        def _walk(idx: int) -> None:
            if idx in seen:
                return
            seen.add(idx)
            result.append(idx)
            for child in tree.children(idx):
                if child.dep == "conj" and child.pos in ("NOUN", "PROPN", "ADJ"):
                    _walk(child.idx)

        _walk(head_idx)
        return result

    def _subject_phrase_text(self, tree: DependencyTree, idx: int) -> str:
        """Get text of a noun head with its pre-modifiers and of-complements."""
        head = tree.token_by_idx(idx)
        if not head:
            return ""
        tokens = [head]
        for child in tree.children(idx):
            if child.dep in ("det", "amod", "compound", "nmod:poss", "nummod", "advmod"):
                tokens.extend(tree.subtree_tokens(child.idx))
            # Include nmod:of (essential noun complement)
            if child.dep == "nmod":
                case_tokens = [c for c in tree.children(child.idx) if c.dep == "case"]
                if case_tokens:
                    case_lemma = case_tokens[0].lemma
                    if case_lemma in ("of", "for", "in", "on", "with", "by", "to"):
                        tokens.extend(tree.subtree_tokens(child.idx))
        tokens.sort(key=lambda t: t.idx)
        return " ".join(t.text for t in tokens if not t.is_punct and not t.is_space)

    def _process_complement(
        self, tree: DependencyTree, complement: TokenInfo,
        subject_text: str, predicate: str, ctx: ExtractionContext
    ) -> list[Statement]:
        statements: list[Statement] = []
        subject = ctx.get_or_create_concept(subject_text)
        object_text = self._object_text(tree, complement.idx)
        if not object_text:
            return statements
        obj = ctx.get_or_create_concept(object_text)
        statements.append(Statement(
            id=StatementID.new(), type=StatementType.FACT,
            subject=subject, predicate=predicate, object=obj,
            sentence_text=ctx.sentence_text,
        ))
        return statements

    def extract(self, tree: DependencyTree, ctx: ExtractionContext) -> list[Statement]:
        statements: list[Statement] = []

        for cop_token in tree.find_by_dep("cop"):
            complement = tree.token_by_idx(cop_token.head_idx)
            if not complement:
                continue

            nsubj_tokens = [t for t in tree.children(complement.idx) if t.dep in ("nsubj", "nsubj:outer", "nsubjpass")]
            complement_is_subject = False
            if not nsubj_tokens:
                comp_head = tree.token_by_idx(complement.head_idx)
                if comp_head and comp_head.is_verb:
                    nsubj_tokens = [t for t in tree.children(comp_head.idx)
                                    if t.dep in ("nsubj", "nsubj:outer", "nsubjpass")]
            if not nsubj_tokens:
                # Fallback: complement itself is the subject (Option B)
                if complement.dep in ("nsubj", "nsubj:pass", "nsubj:outer"):
                    nsubj_tokens = [complement]
                    complement_is_subject = True
            if not nsubj_tokens:
                # Fallback: complement is head of ccomp clause — complement IS the subject
                if complement.dep == "ccomp":
                    nsubj_tokens = [complement]
                    complement_is_subject = True
            if not nsubj_tokens:
                continue

            negated = self._is_negated(tree, cop_token.idx)
            predicate = "be not" if negated else cop_token.lemma

            # When complement IS the subject, find the real attr/nmod child for object text
            obj_comp = complement
            if complement_is_subject:
                for c in tree.children(complement.idx):
                    if c.dep in ("attr", "nmod", "amod", "acomp"):
                        obj_comp = c
                        break

            for nsubj in nsubj_tokens:
                subject_idxs = self._collect_conjuncts(tree, nsubj.idx)
                for sidx in subject_idxs:
                    if len(subject_idxs) > 1:
                        subject_text = self._subject_phrase_text(tree, sidx)
                    else:
                        subject_text = tree.subtree_text(sidx)
                    if not subject_text:
                        continue
                    statements.extend(self._process_complement(
                        tree, obj_comp, subject_text, predicate, ctx))

        # Handle AUX-ROOT variant: ROOT is AUX (be) with nsubj/csubj + attr/nmod
        for tok in tree.tokens:
            if tok.dep != "ROOT" or tok.pos not in ("AUX",):
                continue
            if tok.lemma != "be":
                continue
            # Find subject (nsubj or csubj)
            subj = None
            for c in tree.children(tok.idx):
                if c.dep in ("nsubj", "nsubj:outer", "csubj"):
                    subj = c
                    break
            # Find complement (attr or nmod with case that looks like complement)
            comp = None
            for c in tree.children(tok.idx):
                if c.dep in ("attr",):
                    comp = c
                    break
            if subj is None or comp is None:
                continue
            subject_idxs = self._collect_conjuncts(tree, subj.idx)
            negated = self._is_negated(tree, tok.idx)
            pred = "be not" if negated else tok.lemma
            for sidx in subject_idxs:
                if len(subject_idxs) > 1:
                    subject_text = self._subject_phrase_text(tree, sidx)
                else:
                    subject_text = tree.subtree_text(sidx)
                if not subject_text:
                    continue
                statements.extend(self._process_complement(
                    tree, comp, subject_text, pred, ctx))

        return statements

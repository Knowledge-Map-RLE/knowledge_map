from __future__ import annotations

from src.domain.models import Statement, StatementType, StatementID
from src.extractor.context import ExtractionContext
from src.extractor.rules.base import BaseRule
from src.parser.dep_tree import DependencyTree, TokenInfo


RELATIVE_PRONOUNS = {"that", "which", "who", "whom", "whose"}

EXCLUDED_OBJECT_DEPS = {"relcl", "acl:relcl", "advcl", "ccomp", "xcomp", "mark", "dep", "punct", "cc"}


class ActiveVoiceRule(BaseRule):
    """X influences Y → X → influences → Y

    Matches: nsubj + obj/dobj (no copula), including conj verbs.
    Handles verb coordination chain: ``we propose and explore complexity`` →
    both ``we → propose → complexity`` and ``we → explore → complexity``.

    Handles conj from AUX/copula root: ``IPD is ... and affects populations`` →
    ``IPD → affect → populations worldwide``.
    """

    @property
    def name(self) -> str:
        return "active_voice"

    def _collect_verbs(self, tree: DependencyTree, head: TokenInfo) -> list[TokenInfo]:
        verbs: list[TokenInfo] = []
        if head.is_verb:
            verbs.append(head)
        for child in tree.children(head.idx):
            if child.dep == "conj" and child.is_verb:
                verbs.extend(self._collect_verbs(tree, child))
        return verbs

    def matches(self, tree: DependencyTree) -> bool:
        nsubj = tree.find_by_dep("nsubj")
        if not nsubj:
            return False
        for ns in nsubj:
            head = tree.token_by_idx(ns.head_idx)
            if not head:
                continue
            for v in self._collect_verbs(tree, head):
                has_cop = any(c.dep == "cop" for c in tree.children(v.idx))
                if has_cop:
                    continue
                has_obj = any(c.dep in ("obj", "dobj") for c in tree.children(v.idx))
                has_xcomp = any(c.dep == "xcomp" and c.is_verb for c in tree.children(v.idx))
                if has_obj or has_xcomp:
                    return True
        return False

    def _head_phrase_text(self, tree: DependencyTree, idx: int) -> str:
        """Get text of a noun head and its pre-modifiers only (no clausal dependents)."""
        head = tree.token_by_idx(idx)
        if not head:
            return ""
        tokens = [head]
        for child in tree.children(idx):
            if child.dep in ("det", "amod", "compound", "nmod:poss", "nummod", "advmod"):
                tokens.extend(tree.subtree_tokens(child.idx))
        tokens.sort(key=lambda t: t.idx)
        return " ".join(t.text for t in tokens if not t.is_punct and not t.is_space)

    def _resolve_subject(self, nsubj: TokenInfo, tree: DependencyTree) -> str | None:
        """Resolve relative pronoun subject to its antecedent."""
        if nsubj.lemma not in RELATIVE_PRONOUNS:
            return None
        verb = tree.token_by_idx(nsubj.head_idx)
        if not verb or verb.dep not in ("acl:relcl", "relcl"):
            return None
        antecedent = tree.token_by_idx(verb.head_idx)
        if not antecedent:
            return None
        # If antecedent has its own nsubj, use that (copular chain)
        ant_nsubj = [t for t in tree.children(antecedent.idx) if t.dep in ("nsubj", "nsubjpass")]
        if ant_nsubj:
            resolved = tree.subtree_text(ant_nsubj[0].idx)
            if resolved:
                return resolved
        resolved = self._head_phrase_text(tree, antecedent.idx)
        if resolved:
            return resolved
        return None

    def _object_text(self, tree: DependencyTree, verb: TokenInfo, obj_token: TokenInfo) -> str:
        """Get object subtree text excluding relative clauses and examples (such as)."""
        base_tokens = [obj_token]
        for child in tree.children(obj_token.idx):
            if child.dep in EXCLUDED_OBJECT_DEPS:
                continue
            # Exclude nmod subtrees where case is "such as" or "including"
            if child.dep == "nmod":
                case_tokens = [c for c in tree.children(child.idx) if c.dep == "case"]
                if any(c.lemma in ("such", "including", "e.g.", "i.e.") for c in case_tokens):
                    continue
            base_tokens.extend(tree.subtree_tokens(child.idx))
        base_tokens.sort(key=lambda t: t.idx)
        base = " ".join(t.text for t in base_tokens if not t.is_punct and not t.is_space)

        # verb-level advmods and selective nmods that follow the object
        post = []
        for child in tree.children(verb.idx):
            if child.dep == "advmod" and child.idx > obj_token.idx:
                post.extend(tree.subtree_tokens(child.idx))
            if child.dep == "nmod" and child.idx > obj_token.idx:
                case_preps = [c.lemma for c in tree.children(child.idx) if c.dep == "case"]
                if any(p in ("from", "into", "for") for p in case_preps):
                    post.extend(tree.subtree_tokens(child.idx))
        if not post:
            return base
        post.sort(key=lambda t: t.idx)
        return base + " " + " ".join(t.text for t in post if not t.is_punct and not t.is_space)

    def _object_text_xcomp(self, tree: DependencyTree, xcomp_verb: TokenInfo, exclude_idxs: set[int] | None = None) -> str:
        """Build object text from xcomp verb + its complement subtree."""
        tokens = [xcomp_verb]
        for child in tree.children(xcomp_verb.idx):
            if child.dep in ("dobj", "obj", "nmod", "advmod", "attr"):
                for t in tree.subtree_tokens(child.idx):
                    if not exclude_idxs or t.idx not in exclude_idxs:
                        tokens.append(t)
        tokens.sort(key=lambda t: t.idx)
        return " ".join(t.text for t in tokens if not t.is_punct and not t.is_space)

    def extract(self, tree: DependencyTree, ctx: ExtractionContext) -> list[Statement]:
        statements: list[Statement] = []

        for nsubj in tree.find_by_dep("nsubj"):
            head = tree.token_by_idx(nsubj.head_idx)
            if not head:
                continue

            verbs = self._collect_verbs(tree, head)
            if not verbs:
                continue

            subject_text = tree.subtree_text(nsubj.idx)
            if not subject_text:
                continue

            resolved = self._resolve_subject(nsubj, tree)
            if resolved:
                subject_text = resolved
            subject = ctx.get_or_create_concept(subject_text)

            for v in verbs:
                has_cop = any(c.dep == "cop" for c in tree.children(v.idx))
                if has_cop:
                    continue

                # Normal case: verb has dobj/obj
                for obj_token in tree.children(v.idx):
                    if obj_token.dep not in ("obj", "dobj"):
                        continue
                    object_text = self._object_text(tree, v, obj_token)
                    if not object_text:
                        continue
                    obj = ctx.get_or_create_concept(object_text)

                    statement = Statement(
                        id=StatementID.new(),
                        type=StatementType.FACT,
                        subject=subject,
                        predicate=v.lemma,
                        object=obj,
                        sentence_text=ctx.sentence_text,
                    )
                    statements.append(statement)

                # Fallback: verb has xcomp instead of dobj (e.g., involve)
                xcomps = [c for c in tree.children(v.idx) if c.dep == "xcomp" and c.is_verb]
                for xv in xcomps:
                    # Collect all xcomp verbs (including conj chain)
                    xcomp_verbs = [xv]
                    for conj_child in tree.children(xv.idx):
                        if conj_child.dep == "conj" and conj_child.is_verb:
                            xcomp_verbs.append(conj_child)
                    # Each xcomp verb produces its own statement, excluding siblings
                    all_xcomp_idxs = {x.idx for x in xcomp_verbs}
                    for xc_verb in xcomp_verbs:
                        other_idxs = all_xcomp_idxs - {xc_verb.idx}
                        object_text = self._object_text_xcomp(tree, xc_verb, exclude_idxs=other_idxs)
                        if not object_text:
                            continue
                        obj = ctx.get_or_create_concept(object_text)
                        statement = Statement(
                            id=StatementID.new(),
                            type=StatementType.FACT,
                            subject=subject,
                            predicate=v.lemma,
                            object=obj,
                            sentence_text=ctx.sentence_text,
                        )
                        statements.append(statement)

        return statements

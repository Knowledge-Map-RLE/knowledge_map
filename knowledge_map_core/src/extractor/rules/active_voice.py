from __future__ import annotations

from src.domain.models import Statement, StatementType, StatementID
from src.extractor.context import ExtractionContext
from src.extractor.rules.base import BaseRule
from src.parser.dep_tree import DependencyTree, TokenInfo


RELATIVE_PRONOUNS = {"that", "which", "who", "whom", "whose"}

EXCLUDED_OBJECT_DEPS = {"relcl", "acl:relcl", "advcl", "ccomp", "xcomp", "mark", "dep", "punct", "cc", "conj"}


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

    def _verb_is_negated(self, tree: DependencyTree, verb_idx: int) -> bool:
        for c in tree.children(verb_idx):
            if c.dep == "neg":
                return True
            if c.dep in ("aux",) and c.pos == "AUX":
                for cc in tree.children(c.idx):
                    if cc.dep == "neg":
                        return True
        return False

    def _collect_verbs(self, tree: DependencyTree, head: TokenInfo) -> list[TokenInfo]:
        verbs: list[TokenInfo] = []
        if head.is_verb or head.is_aux:
            verbs.append(head)
        for child in tree.children(head.idx):
            if child.dep == "conj" and (child.is_verb or child.is_aux):
                verbs.extend(self._collect_verbs(tree, child))
        return verbs

    def _find_shared_object(self, tree: DependencyTree, verbs: list[TokenInfo]) -> TokenInfo | None:
        for v in verbs:
            for c in tree.children(v.idx):
                if c.dep in ("obj", "dobj"):
                    return c
        return None

    def matches(self, tree: DependencyTree) -> bool:
        # Direct nsubj → verb pattern
        for ns in tree.find_by_dep("nsubj"):
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
        # Conj verbs of passive heads (shared nsubjpass subject)
        for nsubjpass in tree.find_by_dep("nsubjpass"):
            passive_head = tree.token_by_idx(nsubjpass.head_idx)
            if not passive_head or not passive_head.is_verb:
                continue
            for cv in tree.children(passive_head.idx):
                if cv.dep == "conj" and cv.is_verb:
                    if any(c.dep in ("obj", "dobj") for c in tree.children(cv.idx)):
                        has_cop = any(c.dep == "cop" for c in tree.children(cv.idx))
                        if not has_cop:
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

    def _subject_phrase_text(self, tree: DependencyTree, idx: int) -> str:
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

    def _collect_conjuncts(self, tree: DependencyTree, head_idx: int) -> list[int]:
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
                if any(p in ("from", "into", "for", "with", "in", "on", "as") for p in case_preps):
                    post.extend(tree.subtree_tokens(child.idx))
        if not post:
            return base
        post.sort(key=lambda t: t.idx)
        return base + " " + " ".join(t.text for t in post if not t.is_punct and not t.is_space)

    def _object_text_xcomp(self, tree: DependencyTree, xcomp_verb: TokenInfo, exclude_idxs: set[int] | None = None) -> str:
        """Build object text from xcomp verb + its complement subtree."""
        has_ccomp = any(c.dep == "ccomp" for c in tree.children(xcomp_verb.idx))
        tokens = []
        if not has_ccomp:
            tokens.append(xcomp_verb)
        for child in tree.children(xcomp_verb.idx):
            if child.dep in ("dobj", "obj", "nmod", "advmod", "attr", "acomp", "oprd", "ccomp"):
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

            # Find shared object across the conj verb chain
            shared_obj = self._find_shared_object(tree, verbs)

            # Resolve subject conjuncts
            resolved = self._resolve_subject(nsubj, tree)
            if resolved:
                subject_texts = [resolved]
                # Try to split resolved antecedent into conjuncts
                verb = tree.token_by_idx(nsubj.head_idx)
                if verb and verb.dep in ("acl:relcl", "relcl"):
                    antecedent = tree.token_by_idx(verb.head_idx)
                    if antecedent:
                        ant_conj_idxs = self._collect_conjuncts(tree, antecedent.idx)
                        if len(ant_conj_idxs) > 1:
                            subject_texts = []
                            for sidx in ant_conj_idxs:
                                st = self._subject_phrase_text(tree, sidx)
                                if st:
                                    subject_texts.append(st)
            else:
                subject_idxs = self._collect_conjuncts(tree, nsubj.idx)
                if len(subject_idxs) <= 1:
                    # No conj split needed — use full subtree text
                    subject_texts = [tree.subtree_text(nsubj.idx)]
                else:
                    subject_texts = []
                    for sidx in subject_idxs:
                        st = self._subject_phrase_text(tree, sidx)
                        if st:
                            subject_texts.append(st)
                    if not subject_texts:
                        subject_texts = [tree.subtree_text(nsubj.idx)]

            for subject_text in subject_texts:
                if not subject_text:
                    continue
                subject = ctx.get_or_create_concept(subject_text)

                for v in verbs:
                    has_cop = any(c.dep == "cop" for c in tree.children(v.idx))
                    if has_cop:
                        continue

                    # First-person narrator: I/We propose that X → extract X's predicate from ccomp
                    extracted_ccomp = False
                    if subject_text.strip() in ("I", "We"):
                        ccomp_verbs = [c for c in tree.children(v.idx) if c.dep == "ccomp" and c.is_verb]
                        if ccomp_verbs:
                            for cc_verb in ccomp_verbs:
                                cc_subjs = [t for t in tree.children(cc_verb.idx) if t.dep == "nsubj"]
                                cc_objs = [t for t in tree.children(cc_verb.idx) if t.dep in ("obj", "dobj")]
                                if cc_subjs and cc_objs:
                                    cc_subj_text = tree.subtree_text(cc_subjs[0].idx)
                                    cc_obj_text = self._object_text(tree, cc_verb, cc_objs[0])
                                    if cc_subj_text and cc_obj_text:
                                        cc_subj = ctx.get_or_create_concept(cc_subj_text)
                                        cc_obj = ctx.get_or_create_concept(cc_obj_text)
                                        cc_negated = self._verb_is_negated(tree, cc_verb.idx)
                                        cc_pred = "not " + cc_verb.lemma if cc_negated else cc_verb.lemma
                                        statements.append(Statement(
                                            id=StatementID.new(),
                                            type=StatementType.FACT,
                                            subject=cc_subj,
                                            predicate=cc_pred,
                                            object=cc_obj,
                                            sentence_text=ctx.sentence_text,
                                        ))
                                        extracted_ccomp = True
                    if extracted_ccomp:
                        continue  # Skip normal extraction for I/We ccomp verbs

                    # Collect direct objects
                    obj_tokens = [c for c in tree.children(v.idx) if c.dep in ("obj", "dobj")]

                    # If no direct object, try shared object from conj chain
                    if not obj_tokens and shared_obj is not None:
                        obj_tokens = [shared_obj]

                    for obj_token in obj_tokens:
                        # Split object conjuncts (each conjunct produces its own object)
                        obj_idxs = self._collect_conjuncts(tree, obj_token.idx)
                        for oidx in obj_idxs:
                            o_token = tree.token_by_idx(oidx)
                            if not o_token:
                                continue
                            object_text = self._object_text(tree, v, o_token)
                            if not object_text:
                                continue
                            obj = ctx.get_or_create_concept(object_text)
                            negated = self._verb_is_negated(tree, v.idx)
                            predicate = "not " + v.lemma if negated else v.lemma

                            statement = Statement(
                                id=StatementID.new(),
                                type=StatementType.FACT,
                                subject=subject,
                                predicate=predicate,
                                object=obj,
                                sentence_text=ctx.sentence_text,
                            )
                            statements.append(statement)

                    # Complex transitive: verb has obj + acomp (e.g., make X resistant, render X tangible)
                    acomp_tokens = [c for c in tree.children(v.idx) if c.dep == "acomp"]
                    if obj_tokens and acomp_tokens:
                        for obj_tok in obj_tokens:
                            for acomp_tok in acomp_tokens:
                                combined_by_idx = {}
                                for t in tree.subtree_tokens(obj_tok.idx):
                                    combined_by_idx[t.idx] = t
                                for t in tree.subtree_tokens(acomp_tok.idx):
                                    combined_by_idx[t.idx] = t
                                combined = sorted(combined_by_idx.values(), key=lambda t: t.idx)
                                object_text = " ".join(t.text for t in combined if not t.is_punct and not t.is_space)
                                if not object_text:
                                    continue
                                obj = ctx.get_or_create_concept(object_text)
                                negated = self._verb_is_negated(tree, v.idx)
                                predicate = "not " + v.lemma if negated else v.lemma
                                statement = Statement(
                                    id=StatementID.new(), type=StatementType.FACT,
                                    subject=subject, predicate=predicate, object=obj,
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
                            # Check if xcomp verb has its own object AND a "to" mark (e.g., "needs to integrate")
                            # vs bare gerund xcomp (e.g., "involves substituting") which should keep old behavior
                            xv_has_obj = any(c.dep in ("obj", "dobj") for c in tree.children(xc_verb.idx))
                            xv_has_mark = any(c.dep == "mark" for c in tree.children(xc_verb.idx))
                            if xv_has_obj and xv_has_mark:
                                # Combined predicate: main_verb + to + xcomp_verb
                                mark_text = ""
                                for c in tree.children(xc_verb.idx):
                                    if c.dep == "mark":
                                        mark_text = c.text
                                        break
                                negated = self._verb_is_negated(tree, v.idx) or self._verb_is_negated(tree, xc_verb.idx)
                                pred = "not " + v.lemma if negated else v.lemma
                                if mark_text:
                                    pred += " " + mark_text + " " + xc_verb.lemma
                                else:
                                    pred += " " + xc_verb.lemma
                                # Object: xcomp verb's obj/dobj conjuncts
                                obj_tokens = [c for c in tree.children(xc_verb.idx) if c.dep in ("obj", "dobj")]
                                for obj_token in obj_tokens:
                                    obj_idxs = self._collect_conjuncts(tree, obj_token.idx)
                                    for oidx in obj_idxs:
                                        o_token = tree.token_by_idx(oidx)
                                        if not o_token:
                                            continue
                                        object_text = self._object_text(tree, xc_verb, o_token)
                                        if not object_text:
                                            continue
                                        obj = ctx.get_or_create_concept(object_text)
                                        statement = Statement(
                                            id=StatementID.new(), type=StatementType.FACT,
                                            subject=subject, predicate=pred, object=obj,
                                            sentence_text=ctx.sentence_text,
                                        )
                                        statements.append(statement)
                            else:
                                # Fallback: no object on xcomp verb — use old behavior
                                exclude_idxs = all_xcomp_idxs - {xc_verb.idx}
                                object_text = self._object_text_xcomp(tree, xc_verb, exclude_idxs=exclude_idxs)
                                if not object_text:
                                    continue
                                obj = ctx.get_or_create_concept(object_text)
                                negated = self._verb_is_negated(tree, v.idx)
                                pred = "not " + v.lemma if negated else v.lemma
                                statement = Statement(
                                    id=StatementID.new(),
                                    type=StatementType.FACT,
                                    subject=subject,
                                    predicate=pred,
                                    object=obj,
                                    sentence_text=ctx.sentence_text,
                                )
                                statements.append(statement)

        # Handle conj verbs of passive heads: shared nsubjpass subject
        for nsubjpass in tree.find_by_dep("nsubjpass"):
            passive_head = tree.token_by_idx(nsubjpass.head_idx)
            if not passive_head or not passive_head.is_verb:
                continue
            subject_text = tree.subtree_text(nsubjpass.idx)
            if not subject_text:
                continue
            conj_verbs = [c for c in tree.children(passive_head.idx)
                          if c.dep == "conj" and c.is_verb]
            for cv in conj_verbs:
                has_cop = any(c.dep == "cop" for c in tree.children(cv.idx))
                if has_cop:
                    continue
                has_obj = any(c.dep in ("obj", "dobj") for c in tree.children(cv.idx))
                if not has_obj:
                    continue
                subject = ctx.get_or_create_concept(subject_text)
                for obj_token in tree.children(cv.idx):
                    if obj_token.dep not in ("obj", "dobj"):
                        continue
                    obj_idxs = self._collect_conjuncts(tree, obj_token.idx)
                    for oidx in obj_idxs:
                        o_token = tree.token_by_idx(oidx)
                        if not o_token:
                            continue
                        object_text = self._object_text(tree, cv, o_token)
                        if not object_text:
                            continue
                        obj = ctx.get_or_create_concept(object_text)
                        negated = self._verb_is_negated(tree, cv.idx)
                        pred = "not " + cv.lemma if negated else cv.lemma
                        statement = Statement(
                            id=StatementID.new(),
                            type=StatementType.FACT,
                            subject=subject,
                            predicate=pred,
                            object=obj,
                            sentence_text=ctx.sentence_text,
                        )
                        statements.append(statement)

        return statements

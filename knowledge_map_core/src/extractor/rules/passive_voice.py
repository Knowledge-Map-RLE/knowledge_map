from __future__ import annotations

from src.domain.models import Statement, StatementType, StatementID, Concept
from src.extractor.context import ExtractionContext
from src.extractor.rules.base import BaseRule
from src.parser.dep_tree import DependencyTree, TokenInfo


RELATIVE_PRONOUNS = {"that", "which", "who", "whom", "whose"}
AGENT_PREPOS = {"by", "via", "to", "in", "for", "with", "on", "near", "as"}
DISCOURSE_NOUNS = {"turn", "addition", "contrast", "example", "particular", "conclusion", "summary", "short"}


class PassiveVoiceRule(BaseRule):
    """X was characterized by Y → X → be characterized by → Y

    Matches: nsubjpass + auxpass  OR  acl past-participle with by-agent.
    Also handles linking prepositions (to, in, for) for verbs like "linked to", "involved in".
    Preserves passive voice: subject=nsubjpass/acl-head, predicate=be+verb+prep, object=agent.
    Examples:
      - The syndrome is characterized by bradykinesia.
      - PD is influenced by genetic factors.
      - The process is controlled via PINK1.
      - PD has been linked to living in a rural environment.
      - an age-related multifactorial disease, influenced by both genetic and environmental factors.
    """

    @property
    def name(self) -> str:
        return "passive_voice"

    def matches(self, tree: DependencyTree) -> bool:
        nsubjpass = tree.find_by_dep("nsubj:pass") or tree.find_by_dep("nsubjpass")
        auxpass = tree.find_by_dep("aux:pass") or tree.find_by_dep("auxpass")
        if len(nsubjpass) > 0 and len(auxpass) > 0:
            return True
        if len(auxpass) > 0 and len(tree.find_by_dep("nsubj")) > 0:
            return True
        for t in tree.tokens:
            if t.dep not in ("acl", "advcl") or not t.is_verb:
                continue
            if self._find_agent_nmods(tree, t.idx):
                return True
        return False

    def _verb_is_negated(self, tree: DependencyTree, verb_idx: int) -> bool:
        for c in tree.children(verb_idx):
            if c.dep == "neg":
                return True
            if c.dep in ("aux", "auxpass", "aux:pass"):
                for cc in tree.children(c.idx):
                    if cc.dep == "neg":
                        return True
        return False

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

        return self._resolve_acl_head_subject(antecedent, tree)

    def _resolve_acl_head_subject(self, head: TokenInfo, tree: DependencyTree) -> str | None:
        """Resolve subject from a modified noun. Avoids leaking acl clauses."""
        ant_nsubj = [t for t in tree.children(head.idx)
                     if t.dep in ("nsubj", "nsubj:pass", "nsubjpass")]
        if ant_nsubj:
            resolved = tree.subtree_text(ant_nsubj[0].idx)
            if resolved:
                return resolved
        # Use _subject_phrase_text to exclude clausal modifiers (acl, relcl, advcl)
        resolved = self._subject_phrase_text(tree, head.idx)
        if resolved:
            return resolved
        # Fallback to plain head text (no subtree)
        return head.text

    def _subject_phrase_text(self, tree: DependencyTree, idx: int) -> str:
        """Get noun phrase text excluding clausal modifiers (acl, relcl, advcl)."""
        head = tree.token_by_idx(idx)
        if not head:
            return ""
        tokens = [head]
        for child in tree.children(idx):
            if child.dep in ("acl", "relcl", "advcl", "ccomp", "xcomp", "mark", "punct"):
                continue
            tokens.extend(tree.subtree_tokens(child.idx))
        tokens.sort(key=lambda t: t.idx)
        return " ".join(t.text for t in tokens if not t.is_punct and not t.is_space)

    def _find_agent_nmods(self, tree: DependencyTree, verb_idx: int) -> list[TokenInfo]:
        """Recursively find all agent nmods (including nested ones) in verb's subtree."""
        found: list[TokenInfo] = []
        seen: set[int] = set()
        def _walk(idx: int) -> None:
            for c in tree.children(idx):
                if c.idx in seen:
                    continue
                seen.add(c.idx)
                for cc in tree.children(c.idx):
                    if cc.dep == "case" and cc.lemma in AGENT_PREPOS:
                        found.append(c)
                        break
                _walk(c.idx)
        _walk(verb_idx)
        return found

    def _build_agent_statements(
        self, verb_token: TokenInfo, subject: Statement, tree: DependencyTree, ctx: ExtractionContext
    ) -> list[Statement]:
        """Build statements from verb + agent-by pattern (shared by standard and acl passive)."""
        statements: list[Statement] = []

        agent_tokens = self._find_agent_nmods(tree, verb_token.idx)
        if not agent_tokens:
            return statements

        for agent_nmod in agent_tokens:
            case_prep = ""
            for c in tree.children(agent_nmod.idx):
                if c.dep == "case":
                    case_prep = c.lemma
                    break

            # Skip discourse-level nmods (e.g. "in turn", "in addition")
            if agent_nmod.lemma in DISCOURSE_NOUNS:
                continue

            agent_idxs = self._collect_conjuncts(tree, agent_nmod.idx)

            for head_idx in agent_idxs:
                head = tree.token_by_idx(head_idx)
                if not head:
                    continue
                # Agent text = head + modifiers, but exclude nested agent PPs
                tokens = [head]
                for c in tree.children(head_idx):
                    if c.dep in ("case", "conj", "cc", "neg", "dep", "acl", "relcl", "advcl", "punct", "mark"):
                        continue
                    # Skip nmods with agent prepositions (separate PPs like "by X")
                    if c.dep == "nmod" and any(cc.dep == "case" and cc.lemma in AGENT_PREPOS for cc in tree.children(c.idx)):
                        continue
                    tokens.extend(tree.subtree_tokens(c.idx))
                tokens.sort(key=lambda t: t.idx)
                agent_text = " ".join(t.text for t in tokens if not t.is_punct and not t.is_space)
                if not agent_text:
                    continue
                obj = ctx.get_or_create_concept(agent_text)
                normalized_prep = case_prep.replace("via", "by") if case_prep else ""
                base_pred = f"be {verb_token.text} {normalized_prep}" if normalized_prep else f"be {verb_token.text}"
                negated = self._verb_is_negated(tree, verb_token.idx)
                predicate = "be not " + base_pred[3:] if negated else base_pred

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

    def _build_xcomp_statements(
        self, verb_token: TokenInfo, subject: Statement, tree: DependencyTree, ctx: ExtractionContext
    ) -> list[Statement]:
        """Build statements from verb + xcomp with mark 'to' (e.g. be required to coordinate)."""
        statements: list[Statement] = []

        xcomps = [c for c in tree.children(verb_token.idx) if c.dep == "xcomp"]
        for xc in xcomps:
            has_to = any(c.dep == "mark" and c.lemma == "to" for c in tree.children(xc.idx))
            if not has_to:
                continue

            # Collect xcomp verb and its conj-chain
            xcomp_verbs = [xc]
            for c in tree.children(xc.idx):
                if c.dep == "conj" and c.is_verb:
                    xcomp_verbs.append(c)

            for xv in xcomp_verbs:
                tokens = [xv]
                for c in tree.children(xv.idx):
                    if c.dep in ("dobj", "obj", "nmod", "advmod", "attr", "xcomp"):
                        tokens.extend(tree.subtree_tokens(c.idx))
                tokens.sort(key=lambda t: t.idx)
                obj_text = " ".join(t.text for t in tokens if not t.is_punct and not t.is_space)
                if not obj_text:
                    continue
                obj = ctx.get_or_create_concept(obj_text)
                negated = self._verb_is_negated(tree, verb_token.idx)
                predicate = f"be not {verb_token.text} to" if negated else f"be {verb_token.text} to"
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

    def _build_prep_statements(
        self, verb_token: TokenInfo, subject: Concept, tree: DependencyTree, ctx: ExtractionContext
    ) -> list[Statement]:
        """Build statements from verb + preposition complement without agent.

        Handles: be understood on, be manifested on, be shown in, be published in, etc.
        """
        statements: list[Statement] = []

        for child in tree.children(verb_token.idx):
            if child.dep not in ("nmod", "obl") and child.dep != "advmod":
                continue
            case_preps = [c.lemma for c in tree.children(child.idx) if c.dep == "case"]
            if not case_preps:
                continue
            prep = case_preps[0]
            if prep not in AGENT_PREPOS:
                continue

            complement_idxs = self._collect_conjuncts(tree, child.idx)
            for cidx in complement_idxs:
                c_token = tree.token_by_idx(cidx)
                if not c_token:
                    continue
                tokens = [c_token]
                for cc in tree.children(cidx):
                    if cc.dep in ("case", "conj", "cc", "neg", "dep", "acl", "relcl", "advcl", "punct", "mark"):
                        continue
                    tokens.extend(tree.subtree_tokens(cc.idx))
                tokens.sort(key=lambda t: t.idx)
                obj_text = " ".join(t.text for t in tokens if not t.is_punct and not t.is_space)
                if not obj_text:
                    continue
                obj = ctx.get_or_create_concept(obj_text)
                negated = self._verb_is_negated(tree, verb_token.idx)
                predicate = "be not " + verb_token.text + " " + prep if negated else "be " + verb_token.text + " " + prep
                statements.append(Statement(
                    id=StatementID.new(), type=StatementType.FACT,
                    subject=subject, predicate=predicate, object=obj,
                    sentence_text=ctx.sentence_text,
                ))

        return statements

    def extract(self, tree: DependencyTree, ctx: ExtractionContext) -> list[Statement]:
        statements: list[Statement] = []

        # Standard: nsubj:pass + aux:pass
        processed_verbs: set[int] = set()
        nsubjpass_list = tree.find_by_dep("nsubj:pass") or tree.find_by_dep("nsubjpass")
        for nsubj in nsubjpass_list:
            verb_idx = nsubj.head_idx
            verb = tree.token_by_idx(verb_idx)
            if not verb:
                continue
            processed_verbs.add(verb_idx)

            subject_text = tree.subtree_text(nsubj.idx)
            if not subject_text:
                continue

            resolved = self._resolve_subject(nsubj, tree)
            if resolved:
                subject_text = resolved

            subject = ctx.get_or_create_concept(subject_text)
            agent_stmts = self._build_agent_statements(verb, subject, tree, ctx)
            statements.extend(agent_stmts)
            statements.extend(self._build_xcomp_statements(verb, subject, tree, ctx))
            # Fallback: if no agent found, try preposition complement
            if not agent_stmts:
                statements.extend(self._build_prep_statements(verb, subject, tree, ctx))

        # Fallback: nsubj + aux:pass (UD annotation variation)
        if not (tree.find_by_dep("nsubj:pass") or tree.find_by_dep("nsubjpass")):
            for nsubj in tree.find_by_dep("nsubj"):
                verb_idx = nsubj.head_idx
                if verb_idx in processed_verbs:
                    continue
                verb = tree.token_by_idx(verb_idx)
                if not verb:
                    continue
                has_auxpass = any(c.dep in ("aux:pass", "auxpass") for c in tree.children(verb_idx))
                if not has_auxpass:
                    continue
                processed_verbs.add(verb_idx)
                subject_text = tree.subtree_text(nsubj.idx)
                if not subject_text:
                    continue
                subject = ctx.get_or_create_concept(subject_text)
                agent_stmts = self._build_agent_statements(verb, subject, tree, ctx)
                statements.extend(agent_stmts)
                statements.extend(self._build_xcomp_statements(verb, subject, tree, ctx))
                if not agent_stmts:
                    statements.extend(self._build_prep_statements(verb, subject, tree, ctx))

        for t in tree.tokens:
            if t.dep not in ("acl", "advcl") or not t.is_verb:
                continue

            agent_nmods = self._find_agent_nmods(tree, t.idx)
            head = tree.token_by_idx(t.head_idx)
            if not head:
                continue

            subject_text = self._resolve_acl_head_subject(head, tree)
            if not subject_text:
                continue

            subject = ctx.get_or_create_concept(subject_text)
            if agent_nmods:
                statements.extend(self._build_agent_statements(t, subject, tree, ctx))
            else:
                statements.extend(self._build_prep_statements(t, subject, tree, ctx))

        return statements

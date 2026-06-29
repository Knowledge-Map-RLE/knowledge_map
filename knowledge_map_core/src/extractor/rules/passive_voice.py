from __future__ import annotations

from src.domain.models import Statement, StatementType, StatementID
from src.extractor.context import ExtractionContext
from src.extractor.rules.base import BaseRule
from src.parser.dep_tree import DependencyTree, TokenInfo


RELATIVE_PRONOUNS = {"that", "which", "who", "whom", "whose"}
AGENT_PREPOS = {"by", "via", "to", "in", "for"}


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
        nsubjpass = tree.find_by_dep("nsubjpass")
        auxpass = tree.find_by_dep("auxpass")
        if len(nsubjpass) > 0 and len(auxpass) > 0:
            return True
        for t in tree.tokens:
            if t.dep == "acl" and t.is_verb:
                for c in tree.children(t.idx):
                    if c.dep == "nmod" and any(
                        c2.dep == "case" and c2.lemma in AGENT_PREPOS
                        for c2 in tree.children(c.idx)
                    ):
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
                if child.dep == "conj":
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
        """Resolve subject from a modified noun's copular subject if available."""
        ant_nsubj = [t for t in tree.children(head.idx)
                     if t.dep in ("nsubj", "nsubjpass")]
        if ant_nsubj:
            resolved = tree.subtree_text(ant_nsubj[0].idx)
            if resolved:
                return resolved
        resolved = tree.subtree_text(head.idx)
        if resolved:
            return resolved
        return None

    def _build_agent_statements(
        self, verb_token: TokenInfo, subject: Statement, tree: DependencyTree, ctx: ExtractionContext
    ) -> list[Statement]:
        """Build statements from verb + agent-by pattern (shared by standard and acl passive)."""
        statements: list[Statement] = []

        nmod_tokens = [t for t in tree.children(verb_token.idx) if t.dep == "nmod"]
        agent_tokens = [
            nm for nm in nmod_tokens
            if any(c.dep == "case" and c.lemma in AGENT_PREPOS for c in tree.children(nm.idx))
        ]
        if not agent_tokens:
            return statements

        for agent_nmod in agent_tokens:
            case_prep = ""
            for c in tree.children(agent_nmod.idx):
                if c.dep == "case":
                    case_prep = c.lemma
                    break

            agent_idxs = self._collect_conjuncts(tree, agent_nmod.idx)

            for head_idx in agent_idxs:
                head = tree.token_by_idx(head_idx)
                if not head:
                    continue
                tokens = [head]
                excluded_deps = {"case", "conj", "cc"}
                for c in tree.children(head_idx):
                    if c.dep in excluded_deps:
                        continue
                    tokens.extend(tree.subtree_tokens(c.idx))
                tokens.sort(key=lambda t: t.idx)
                agent_text = " ".join(t.text for t in tokens if not t.is_punct and not t.is_space)
                if not agent_text:
                    continue
                obj = ctx.get_or_create_concept(agent_text)
                normalized_prep = case_prep.replace("via", "by") if case_prep else ""
                predicate = f"be {verb_token.text} {normalized_prep}" if normalized_prep else f"be {verb_token.text}"

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

        for nsubj in tree.find_by_dep("nsubjpass"):
            verb_idx = nsubj.head_idx
            verb = tree.token_by_idx(verb_idx)
            if not verb:
                continue

            subject_text = tree.subtree_text(nsubj.idx)
            if not subject_text:
                continue

            resolved = self._resolve_subject(nsubj, tree)
            if resolved:
                subject_text = resolved

            subject = ctx.get_or_create_concept(subject_text)
            statements.extend(self._build_agent_statements(verb, subject, tree, ctx))

        for t in tree.tokens:
            if t.dep != "acl" or not t.is_verb:
                continue

            nmod_check = [c for c in tree.children(t.idx) if c.dep == "nmod"]
            has_by_agent = any(
                c.dep == "case" and c.lemma in AGENT_PREPOS
                for nm in nmod_check
                for c in tree.children(nm.idx)
            )
            if not has_by_agent:
                continue

            head = tree.token_by_idx(t.head_idx)
            if not head:
                continue

            subject_text = self._resolve_acl_head_subject(head, tree)
            if not subject_text:
                continue

            subject = ctx.get_or_create_concept(subject_text)
            statements.extend(self._build_agent_statements(t, subject, tree, ctx))

        return statements

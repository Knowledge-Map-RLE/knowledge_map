from __future__ import annotations

from src.domain.models import Statement, StatementType, StatementID
from src.extractor.context import ExtractionContext
from src.extractor.rules.base import BaseRule
from src.parser.dep_tree import DependencyTree


AGENT_PREPOS = {"by", "via", "to", "in", "for", "with", "on", "near"}

MODAL_AUXES = {"can", "could", "will", "would", "shall", "should", "may", "might", "must"}


class NegationRule(BaseRule):
    """X is not Y → X → is → Y (negated)

    Matches: neg dependency
    Examples:
      - Lewy bodies are typically lacking.
      - NAD+ is not synthesized in the cytosol.
      - PD is not caused by a single factor.
      - heterogeneous disease progression cannot be understood with unidimensional approaches.
    """

    @property
    def name(self) -> str:
        return "negation"

    def matches(self, tree: DependencyTree) -> bool:
        neg_tokens = tree.find_by_dep("neg")
        return len(neg_tokens) > 0

    def _find_main_verb(self, tree: DependencyTree, verb_idx: int):
        """If verb is a modal aux, return its xcomp main verb."""
        verb = tree.token_by_idx(verb_idx)
        if not verb:
            return None, ""
        xcomps = [c for c in tree.children(verb.idx) if c.dep == "xcomp" and c.is_verb]
        if xcomps:
            return xcomps[0], verb.lemma
        return verb, ""

    def _find_nsubj(self, tree, verb_idx, main_verb):
        """Find nsubj from main verb or its parent modal."""
        nsubj = [t for t in tree.children(main_verb.idx) if t.dep in ("nsubj", "nsubj:pass", "nsubj:outer")]
        if not nsubj and verb_idx != main_verb.idx:
            nsubj = [t for t in tree.children(verb_idx) if t.dep in ("nsubj", "nsubj:pass")]
        return nsubj

    def _find_agent_prep(self, tree, main_verb_idx):
        """Find agent preposition from a (passive) main verb, like 'with' in 'understood with'."""
        for c in tree.children(main_verb_idx):
            if c.dep == "nmod":
                for cc in tree.children(c.idx):
                    if cc.dep == "case" and cc.lemma in AGENT_PREPOS:
                        return cc.lemma, c.idx
        return None, None

    def extract(self, tree: DependencyTree, ctx: ExtractionContext) -> list[Statement]:
        statements: list[Statement] = []

        for neg in tree.find_by_dep("neg"):
            verb = tree.token_by_idx(neg.head_idx)
            if not verb:
                continue

            main_verb, modal_lemma = self._find_main_verb(tree, neg.head_idx)
            nsubj = self._find_nsubj(tree, neg.head_idx, main_verb)
            if not nsubj:
                continue

            nsubj_text = tree.subtree_text(nsubj[0].idx)
            if not nsubj_text:
                continue
            subject = ctx.get_or_create_concept(nsubj_text)

            neg_marker = tree.subtree_text(neg.idx)

            # Check for agent preposition on main verb (e.g., "understood with")
            agent_prep, agent_nmod_idx = self._find_agent_prep(tree, main_verb.idx)

            if agent_prep and agent_nmod_idx is not None:
                agent_text = tree.subtree_text(agent_nmod_idx)
                if agent_text:
                    obj = ctx.get_or_create_concept(agent_text)
                    pred_parts = ["not"]
                    if modal_lemma:
                        pred_parts.append(modal_lemma)
                    pred_parts.append(main_verb.lemma)
                    pred_parts.append(agent_prep)
                    predicate = " ".join(pred_parts)

                    statement = Statement(
                        id=StatementID.new(),
                        type=StatementType.FACT,
                        subject=subject,
                        predicate=predicate,
                        object=obj,
                        sentence_text=ctx.sentence_text,
                        metadata={"negation": neg_marker},
                    )
                    statements.append(statement)
                    continue

            obj_tokens = [t for t in tree.children(main_verb.idx) if t.dep in ("obj", "dobj", "attr", "adj", "acomp")]

            predicate_parts = ["not"]
            if modal_lemma:
                predicate_parts.append(modal_lemma)
            predicate_parts.append(main_verb.lemma if main_verb.lemma else verb.lemma)
            predicate = " ".join(predicate_parts)

            if obj_tokens:
                for obj_token in obj_tokens:
                    object_text = tree.subtree_text(obj_token.idx)
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
                        metadata={"negation": neg_marker},
                    )
                    statements.append(statement)
            else:
                verb_phrase = tree.subtree_text(main_verb.idx)
                obj = ctx.get_or_create_concept(verb_phrase or main_verb.lemma)
                statement = Statement(
                    id=StatementID.new(),
                    type=StatementType.FACT,
                    subject=subject,
                    predicate=predicate,
                    object=obj,
                    sentence_text=ctx.sentence_text,
                    metadata={"negation": neg_marker},
                )
                statements.append(statement)

        return statements

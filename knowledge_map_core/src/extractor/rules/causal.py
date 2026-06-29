from __future__ import annotations

from src.domain.models import Statement, StatementType, StatementID
from src.extractor.context import ExtractionContext
from src.extractor.rules.base import BaseRule
from src.parser.dep_tree import DependencyTree


class CausalRule(BaseRule):
    """X causes Y → X → causes → Y

    Matches: advcl with cause/since/because markers, or verbs with causal semantics
    Examples:
      - Mitochondrial dysfunction causes oxidative stress.
      - Loss of DA neurons arises from genetic factors.
      - Because aging is the main risk factor, PD develops later.
    """

    CAUSAL_MARKERS = {"because", "since", "as", "due", "owing", "given"}
    CAUSAL_VERBS = {"cause", "lead", "result", "arise", "derive", "trigger", "induce", "promote", "drive", "contribute", "influence", "affect"}

    @property
    def name(self) -> str:
        return "causal"

    def matches(self, tree: DependencyTree) -> bool:
        advcl = tree.find_by_dep("advcl")
        for clause in advcl:
            markers = [t for t in tree.children(clause.idx) if t.dep == "mark"]
            for m in markers:
                if m.lemma.lower() in self.CAUSAL_MARKERS:
                    return True

        for verb in tree.find_by_pos("VERB"):
            if verb.lemma.lower() in self.CAUSAL_VERBS:
                return True

        return False

    def extract(self, tree: DependencyTree, ctx: ExtractionContext) -> list[Statement]:
        statements: list[Statement] = []

        for verb in tree.find_by_pos("VERB"):
            if verb.lemma.lower() not in self.CAUSAL_VERBS:
                continue

            nsubj = [t for t in tree.children(verb.idx) if t.dep in ("nsubj", "nsubj:pass")]
            obj = [t for t in tree.children(verb.idx) if t.dep in ("obj", "dobj")]

            if not nsubj or not obj:
                continue

            subject_text = tree.subtree_text(nsubj[0].idx)
            object_text = tree.subtree_text(obj[0].idx)
            if not subject_text or not object_text:
                continue

            subject = ctx.get_or_create_concept(subject_text)
            obj_concept = ctx.get_or_create_concept(object_text)

            statement = Statement(
                id=StatementID.new(),
                type=StatementType.FACT,
                subject=subject,
                predicate=verb.lemma,
                object=obj_concept,
                sentence_text=ctx.sentence_text,
            )
            statements.append(statement)

        return statements

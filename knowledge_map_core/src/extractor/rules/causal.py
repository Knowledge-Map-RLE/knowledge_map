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
    CAUSAL_VERBS = {
        "cause", "lead", "result", "arise", "derive", "trigger", "induce",
        "promote", "drive", "contribute", "influence", "affect",
        "enable", "provide", "suppress", "involve", "require",
        "establish", "select", "prevent", "slow",
    }

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

    def _verb_is_negated(self, tree: DependencyTree, verb_idx: int) -> bool:
        for c in tree.children(verb_idx):
            if c.dep == "neg":
                return True
            if c.dep in ("aux",) and c.pos == "AUX":
                for cc in tree.children(c.idx):
                    if cc.dep == "neg":
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
                if child.dep == "conj" and child.pos in ("NOUN", "PROPN", "ADJ"):
                    _walk(child.idx)

        _walk(head_idx)
        return result

    def extract(self, tree: DependencyTree, ctx: ExtractionContext) -> list[Statement]:
        statements: list[Statement] = []

        for verb in tree.find_by_pos("VERB"):
            if verb.lemma.lower() not in self.CAUSAL_VERBS:
                continue

            nsubj = [t for t in tree.children(verb.idx) if t.dep in ("nsubj", "nsubj:pass")]
            obj = [t for t in tree.children(verb.idx) if t.dep in ("obj", "dobj")]

            if not nsubj or not obj:
                continue

            subject_idxs = self._collect_conjuncts(tree, nsubj[0].idx)
            obj_idxs = self._collect_conjuncts(tree, obj[0].idx)

            negated = self._verb_is_negated(tree, verb.idx)
            pred = ("not " + verb.lemma) if negated else verb.lemma

            for sidx in subject_idxs:
                s_token = tree.token_by_idx(sidx)
                if not s_token:
                    continue
                subject_text = tree.subtree_text(sidx)
                if not subject_text:
                    continue
                subject = ctx.get_or_create_concept(subject_text)

                for oidx in obj_idxs:
                    o_token = tree.token_by_idx(oidx)
                    if not o_token:
                        continue
                    object_text = tree.subtree_text(oidx)
                    if not object_text:
                        continue
                    obj_concept = ctx.get_or_create_concept(object_text)

                    statement = Statement(
                        id=StatementID.new(),
                        type=StatementType.FACT,
                        subject=subject,
                        predicate=pred,
                        object=obj_concept,
                        sentence_text=ctx.sentence_text,
                    )
                    statements.append(statement)

        return statements

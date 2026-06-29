from __future__ import annotations

from src.domain.models import Statement, StatementType, StatementID
from src.extractor.context import ExtractionContext
from src.extractor.rules.base import BaseRule
from src.parser.dep_tree import DependencyTree


COPULAR_LIKE = frozenset({
    "represent", "constitute", "form", "comprise", "indicate",
    "reflect", "define", "signify", "mean", "denote",
})


class CopularLikeRule(BaseRule):
    """X represents Y → X → be → Y

    Verbs like 'represent', 'constitute', 'form' that function copularly
    in nsubj → verb → dobj constructions.
    """

    EXCLUDED_DEPS = {"nsubj", "nsubj:outer", "nsubjpass", "nsubj:pass",
                     "cop", "aux", "aux:pass", "auxpass", "mark",
                     "acl", "relcl", "ccomp", "xcomp",
                     "neg", "punct", "dep", "case", "cc"}

    @property
    def name(self) -> str:
        return "copular_like"

    def matches(self, tree: DependencyTree) -> bool:
        for verb in tree.find_by_pos("VERB"):
            if verb.lemma in COPULAR_LIKE and len(tree.find_by_dep("nsubj")) > 0:
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

    def _object_text(self, tree: DependencyTree, complement_idx: int) -> str:
        tokens = [tree.token_by_idx(complement_idx)]
        for child in tree.children(complement_idx):
            if child.dep in self.EXCLUDED_DEPS:
                continue
            tokens.extend(tree.subtree_tokens(child.idx))
        tokens = [t for t in tokens if t and not t.is_punct and not t.is_space]
        tokens.sort(key=lambda t: t.idx)
        return " ".join(t.text for t in tokens)

    def extract(self, tree: DependencyTree, ctx: ExtractionContext) -> list[Statement]:
        statements: list[Statement] = []

        for verb in tree.find_by_pos("VERB"):
            if verb.lemma not in COPULAR_LIKE:
                continue

            nsubj_tokens = [t for t in tree.children(verb.idx) if t.dep in ("nsubj", "nsubj:outer")]
            if not nsubj_tokens:
                continue

            dobj_tokens = [t for t in tree.children(verb.idx) if t.dep in ("dobj", "dative", "attr")]
            if not dobj_tokens:
                continue

            verb_idxs = self._collect_conjuncts(tree, verb.idx)
            dobj_conjuncts = []
            for dobj in dobj_tokens:
                dobj_conjuncts.extend(self._collect_conjuncts(tree, dobj.idx))

            for v_idx in verb_idxs:
                v = tree.token_by_idx(v_idx)
                if not v:
                    continue
                verb_nsubj = [t for t in tree.children(v.idx) if t.dep in ("nsubj", "nsubj:outer")]
                if not verb_nsubj:
                    continue
                for nsubj in verb_nsubj:
                    subject_text = tree.subtree_text(nsubj.idx)
                    if not subject_text:
                        continue

                    subject = ctx.get_or_create_concept(subject_text)

                    for dobj_conjunct in dobj_conjuncts:
                        obj_text = self._object_text(tree, dobj_conjunct)
                        if not obj_text:
                            continue
                        obj = ctx.get_or_create_concept(obj_text)

                        statement = Statement(
                            id=StatementID.new(),
                            type=StatementType.FACT,
                            subject=subject,
                            predicate="be",
                            object=obj,
                            sentence_text=ctx.sentence_text,
                        )
                        statements.append(statement)

        return statements

from __future__ import annotations

from src.domain.models import Statement, StatementType, StatementID
from src.extractor.context import ExtractionContext
from src.extractor.rules.base import BaseRule
from src.parser.dep_tree import DependencyTree


MULTI_WORD_PREDICATES: dict[str, list[list[str]]] = {
    # verb: [[function_word_sequence], ...]
    # e.g. "start prior to" has verb="start", seq=["prior", "to"]
    "start": [["prior", "to"], ["after"], ["in"]],
    "arise": [["from"]],
    "present": [["as"]],
    "lead": [["to"]],
    "evolve": [["into"]],
    "come": [["from"]],
    "translocate": [["to"], ["from"]],
    "correlate": [["with"]],
    "interfere": [["with"]],
    "associate": [["with"]],
    "bind": [["to"]],
    "emerge": [["from"]],
    "focus": [["on"]],
    "propagate": [["between"], ["from"]],
    "spread": [["in"]],
    "react": [["with"]],
    "consist": [["of"]],
    "account": [["for"]],
    "contribute": [["to"]],
    "need": [["to"]],
    "serve": [["to"]],
    "gain": [["PARK status"]],
    "occur": [["in"]],
    "act": [["as"]],
    "result": [["in"]],
    "end": [["with"]],
    "vary": [["with"]],
    "differ": [["in"]],
    "manifest": [["as"]],
    "engage": [["in"]],
    "participate": [["in"]],
    "specialize": [["in"]],
    "originate": [["from"], ["in"]],
    "mediate": [["by"]],
    "mark": [["by"]],
    "characterize": [["by"]],
    "drive": [["by"]],
    "require": [["to"]],
    "implicate": [["in"]],
}


def _build_predicate(verb_lemma: str, seq: list[str]) -> str:
    """Build multi-word predicate string, e.g., 'start prior to'."""
    return " ".join([verb_lemma] + seq)


def _prep_dep_ok(dep: str) -> bool:
    return dep in ("case", "prep", "mark")


class MultiWordPredicateRule(BaseRule):
    """Verb + particle/preposition(s) → predicate preserving multi-word structure.

    Handles:
      - start prior to (hyposmia → start prior to → onset)
      - arise from (motor symptoms → arise from → loss of DA neurons)
      - present as (PD → present as → Mendelian form)
      - lead to (mutations → lead to → fragmentation)
      - evolve into (PD research → evolve into → mature research field)
    """

    @property
    def name(self) -> str:
        return "multi_word_predicate"

    def _verb_is_negated(self, tree: DependencyTree, verb_idx: int) -> bool:
        for c in tree.children(verb_idx):
            if c.dep == "neg":
                return True
            if c.dep in ("aux",):
                for cc in tree.children(c.idx):
                    if cc.dep == "neg":
                        return True
        return False

    def _check_seq_match(
        self, tree: DependencyTree, verb_idx: int, seq: list[str]
    ) -> tuple[bool, int | None]:
        """Check if a function-word sequence follows the verb.

        Returns (matched, nmod_head_idx) where nmod_head_idx is the object head.

        Handles patterns:
          1-word: verb → nmod (head) → case (seq[0])
                  e.g. arise → loss → from
          2-word: verb → seq[0] (advmod) → nmod (head) → seq[1] (case)
                  e.g. start → prior → onset → to
        """
        verb = tree.token_by_idx(verb_idx)
        if not verb:
            return False, None

        if len(seq) == 1:
            # Pattern A: verb → nmod/pobj/dobj (head) → case (seq[0])
            # e.g. arise → loss → from
            for child in tree.children(verb_idx):
                if child.dep in ("nmod", "pobj", "dobj"):
                    for cc in tree.children(child.idx):
                        if cc.dep == "case" and cc.lemma == seq[0]:
                            return True, child.idx
            # Pattern B: verb → prep/advmod/mark (seq[0]) → nmod/pobj/dobj/xcomp
            # e.g. need → to → integrate  OR  start → after → loss
            for child in tree.children(verb_idx):
                if child.lemma == seq[0] and child.dep in ("prep", "case", "mark", "advmod", "prt"):
                    for nmod_child in tree.children(child.idx):
                        if nmod_child.dep in ("nmod", "pobj", "dobj", "xcomp"):
                            return True, nmod_child.idx
            # Pattern C: seq[0] as child of verb with no case (e.g. "gain PARK status")
            for child in tree.children(verb_idx):
                if child.dep in ("nmod", "pobj", "dobj", "attr"):
                    obj_text = " ".join(
                        t.text for t in tree.subtree_tokens(child.idx)
                        if not t.is_punct and not t.is_space
                    )
                    if obj_text and seq[0] in obj_text:
                        return True, child.idx
            return False, None

        if len(seq) == 2:
            # Find: verb → seq[0] → nmod (head) → case (seq[1])
            for ft in tree.children(verb_idx):
                if ft.lemma == seq[0] and ft.dep in ("advmod", "prt", "case", "prep", "mark"):
                    # Check if ft has an nmod child with matching case
                    for nmod_child in tree.children(ft.idx):
                        if nmod_child.dep in ("nmod", "pobj"):
                            for cc in tree.children(nmod_child.idx):
                                if cc.dep == "case" and cc.lemma == seq[1]:
                                    return True, nmod_child.idx
            return False, None

        return False, None

    def matches(self, tree: DependencyTree) -> bool:
        for verb in tree.find_by_pos("VERB"):
            if verb.lemma in MULTI_WORD_PREDICATES:
                for seq in MULTI_WORD_PREDICATES[verb.lemma]:
                    matched, _ = self._check_seq_match(tree, verb.idx, seq)
                    if matched:
                        return True
        return False

    def _collect_conjunct_objects(self, tree: DependencyTree, head_idx: int) -> list[int]:
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

    def _object_text(self, tree: DependencyTree, nmod_idx: int) -> str:
        """Build object text from the predicate's complement head."""
        head = tree.token_by_idx(nmod_idx)
        if not head:
            return ""
        tokens = [head]
        for child in tree.children(nmod_idx):
            if head.is_verb or head.is_aux:
                # Verb complement: include obj/dobj/xcomp/nmod
                if child.dep in ("obj", "dobj", "xcomp", "nmod", "advmod", "attr"):
                    tokens.extend(tree.subtree_tokens(child.idx))
            else:
                # Noun/adj complement: include modifiers
                if child.dep in ("det", "amod", "compound", "nmod:poss", "nummod", "nmod"):
                    tokens.extend(tree.subtree_tokens(child.idx))
        tokens.sort(key=lambda t: t.idx)
        return " ".join(t.text for t in tokens if not t.is_punct and not t.is_space)

    def extract(self, tree: DependencyTree, ctx: ExtractionContext) -> list[Statement]:
        statements: list[Statement] = []

        for verb in tree.find_by_pos("VERB"):
            if verb.lemma not in MULTI_WORD_PREDICATES:
                continue

            for seq in MULTI_WORD_PREDICATES[verb.lemma]:
                matched, nmod_idx = self._check_seq_match(tree, verb.idx, seq)
                if not matched or nmod_idx is None:
                    continue

                # Resolve subject
                # Case 1: verb has direct nsubj or nsubjpass
                # Determine if passive voice (nsubjpass)
                nsubjpass_tokens = [
                    t for t in tree.children(verb.idx) if t.dep == "nsubjpass"
                ]
                is_passive = bool(nsubjpass_tokens)

                nsubj_tokens = [
                    t for t in tree.children(verb.idx)
                    if t.dep in ("nsubj", "nsubj:outer", "nsubjpass")
                ]
                if not nsubj_tokens:
                    # Case 2: verb is xcomp of passive verb (arise from...)
                    head_verb = tree.token_by_idx(verb.head_idx)
                    if head_verb and head_verb.is_verb:
                        for c in tree.children(head_verb.idx):
                            if c.dep in ("nsubj", "nsubjpass"):
                                nsubj_tokens = [c]
                                break

                if not nsubj_tokens:
                    continue

                # Build predicate
                negated = self._verb_is_negated(tree, verb.idx)
                if is_passive:
                    base = "be " + verb.text + " " + " ".join(seq)
                else:
                    base = _build_predicate(verb.lemma, seq)
                predicate = "not " + base if negated else base

                # Collect subjects (including conj)
                subject_idxs = [nsubj_tokens[0].idx]
                for c in tree.children(nsubj_tokens[0].idx):
                    if c.dep == "conj":
                        subject_idxs.append(c.idx)

                object_idxs = self._collect_conjunct_objects(tree, nmod_idx)

                for s_idx in subject_idxs:
                    subject_text = tree.subtree_text(s_idx)
                    if not subject_text:
                        continue

                    subject = ctx.get_or_create_concept(subject_text)

                    for o_idx in object_idxs:
                        obj_text = self._object_text(tree, o_idx)
                        if not obj_text:
                            continue

                        obj = ctx.get_or_create_concept(obj_text)

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

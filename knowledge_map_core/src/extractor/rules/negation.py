from __future__ import annotations

from src.domain.models import Statement, StatementType, StatementID
from src.extractor.context import ExtractionContext
from src.extractor.rules.base import BaseRule
from src.parser.dep_tree import DependencyTree


class NegationRule(BaseRule):
    """X is not Y → X → is → Y (negated)

    Matches: neg dependency
    Examples:
      - Lewy bodies are typically lacking.
      - NAD+ is not synthesized in the cytosol.
      - PD is not caused by a single factor.
    """

    @property
    def name(self) -> str:
        return "negation"

    def matches(self, tree: DependencyTree) -> bool:
        neg_tokens = tree.find_by_dep("neg")
        return len(neg_tokens) > 0

    def extract(self, tree: DependencyTree, ctx: ExtractionContext) -> list[Statement]:
        statements: list[Statement] = []

        for neg in tree.find_by_dep("neg"):
            verb = tree.token_by_idx(neg.head_idx)
            if not verb:
                continue

            nsubj = [t for t in tree.children(verb.idx) if t.dep in ("nsubj", "nsubj:pass")]
            if not nsubj:
                continue

            nsubj_text = tree.subtree_text(nsubj[0].idx)
            if not nsubj_text:
                continue
            subject = ctx.get_or_create_concept(nsubj_text)

            obj_tokens = [t for t in tree.children(verb.idx) if t.dep in ("obj", "dobj", "attr", "adj", "acomp")]

            neg_marker = tree.subtree_text(neg.idx)
            predicate = f"not_{verb.lemma}" if verb.is_verb else f"not_{neg.text}"

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
                verb_phrase = tree.subtree_text(verb.idx)
                obj = ctx.get_or_create_concept(verb_phrase or verb.lemma)
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

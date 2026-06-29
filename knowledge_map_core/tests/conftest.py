from __future__ import annotations

import pytest

from src.domain.models import Concept, Statement, StatementType, StatementID
from src.extractor.context import ExtractionContext
from src.extractor.engine import RuleEngine
from src.parser.dep_tree import DependencyTree, TokenInfo


def make_token(
    idx: int,
    text: str,
    lemma: str = "",
    pos: str = "",
    tag: str = "",
    dep: str = "",
    head_idx: int = 0,
) -> TokenInfo:
    return TokenInfo(
        idx=idx,
        text=text,
        lemma=lemma or text.lower(),
        pos=pos,
        tag=tag,
        dep=dep,
        head_idx=head_idx,
    )


def make_tree(tokens: list[TokenInfo], deps: list[tuple[int, int, str]]) -> DependencyTree:
    for dependent_idx, head_idx, rel in deps:
        for t in tokens:
            if t.idx == dependent_idx:
                t.dep = rel
                t.head_idx = head_idx
                break
    return DependencyTree(tokens=tokens)


def make_context(sentence_text: str = "Test sentence.") -> ExtractionContext:
    return ExtractionContext(sentence_text=sentence_text)


@pytest.fixture
def engine():
    return RuleEngine()


@pytest.fixture
def sample_concepts():
    return {
        "dopamine": Concept(id="c0", text="dopamine"),
        "neurotransmitter": Concept(id="c1", text="neurotransmitter"),
        "parkinson": Concept(id="c2", text="Parkinson's disease"),
        "genetic factors": Concept(id="c3", text="genetic factors"),
        "environmental factors": Concept(id="c4", text="environmental factors"),
    }

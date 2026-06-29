import pytest

from src.extractor.rules.copular import CopularRule
from tests.conftest import make_token, make_tree, make_context


class TestCopularRule:
    @pytest.fixture
    def rule(self):
        return CopularRule()

    def test_matches_copular_sentence(self, rule):
        tokens = [
            make_token(0, "Dopamine", "dopamine", "NOUN", "NN", "", 2),
            make_token(1, "is", "be", "AUX", "VBZ", "", 2),
            make_token(2, "neurotransmitter", "neurotransmitter", "NOUN", "NN", "", 2),
            make_token(3, "a", "a", "DET", "DT", "", 2),
        ]
        deps = [(0, 2, "nsubj"), (1, 2, "cop"), (3, 2, "det")]
        tree = make_tree(tokens, deps)
        assert rule.matches(tree) is True

    def test_does_not_match_without_copula(self, rule):
        tokens = [
            make_token(0, "Dopamine", "dopamine", "NOUN", "NN", "", 1),
            make_token(1, "affects", "affect", "VERB", "VBZ", "", 1),
            make_token(2, "brain", "brain", "NOUN", "NN", "", 1),
        ]
        deps = [(0, 1, "nsubj"), (2, 1, "obj")]
        tree = make_tree(tokens, deps)
        assert rule.matches(tree) is False

    def test_extract_copular_fact(self, rule):
        tokens = [
            make_token(0, "PD", "PD", "NOUN", "NN", "", 2),
            make_token(1, "is", "be", "AUX", "VBZ", "", 2),
            make_token(2, "age-related", "age-related", "ADJ", "JJ", "", 2),
        ]
        deps = [(0, 2, "nsubj"), (1, 2, "cop")]
        tree = make_tree(tokens, deps)
        statements = rule.extract(tree, make_context())
        assert len(statements) == 1
        assert statements[0].subject_id is not None
        assert statements[0].predicate == "be"
        assert statements[0].object_id is not None

    def test_extract_copular_with_determiner(self, rule):
        tokens = [
            make_token(0, "Dopamine", "dopamine", "NOUN", "NN", "", 2),
            make_token(1, "is", "be", "AUX", "VBZ", "", 2),
            make_token(2, "neurotransmitter", "neurotransmitter", "NOUN", "NN", "", 2),
            make_token(3, "a", "a", "DET", "DT", "", 2),
        ]
        deps = [(0, 2, "nsubj"), (1, 2, "cop"), (3, 2, "det")]
        tree = make_tree(tokens, deps)
        statements = rule.extract(tree, make_context())
        assert len(statements) == 1

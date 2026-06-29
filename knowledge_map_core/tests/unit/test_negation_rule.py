import pytest

from src.extractor.rules.negation import NegationRule
from tests.conftest import make_token, make_tree


class TestNegationRule:
    @pytest.fixture
    def rule(self):
        return NegationRule()

    def test_matches_negation(self, rule):
        tokens = [
            make_token(0, "Lewy", "Lewy", "PROPN", "NNP", "compound", 1),
            make_token(1, "bodies", "body", "NOUN", "NNS", "nsubj", 2),
            make_token(2, "are", "be", "AUX", "VBP", "ROOT", 2),
            make_token(3, "not", "not", "PART", "RB", "neg", 2),
            make_token(4, "present", "present", "ADJ", "JJ", "acomp", 2),
        ]
        deps = [(0, 1, "compound"), (1, 2, "nsubj"), (3, 2, "neg"), (4, 2, "acomp")]
        tree = make_tree(tokens, deps)
        assert rule.matches(tree) is True

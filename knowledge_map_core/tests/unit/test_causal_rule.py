import pytest

from src.extractor.rules.causal import CausalRule
from tests.conftest import make_token, make_tree


class TestCausalRule:
    @pytest.fixture
    def rule(self):
        return CausalRule()

    def test_matches_causal_verb(self, rule):
        tokens = [
            make_token(0, "Mitochondrial", "mitochondrial", "ADJ", "JJ", "amod", 1),
            make_token(1, "dysfunction", "dysfunction", "NOUN", "NN", "nsubj", 3),
            make_token(2, "causes", "cause", "VERB", "VBZ", "ROOT", 2),
            make_token(3, "oxidative", "oxidative", "ADJ", "JJ", "amod", 4),
            make_token(4, "stress", "stress", "NOUN", "NN", "obj", 2),
        ]
        deps = [(0, 1, "amod"), (1, 2, "nsubj"), (3, 4, "amod"), (4, 2, "obj")]
        tree = make_tree(tokens, deps)
        assert rule.matches(tree) is True

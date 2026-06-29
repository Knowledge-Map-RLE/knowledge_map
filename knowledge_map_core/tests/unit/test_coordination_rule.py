import pytest

from src.extractor.rules.coordination import CoordinationRule
from tests.conftest import make_token, make_tree


class TestCoordinationRule:
    @pytest.fixture
    def rule(self):
        return CoordinationRule()

    def test_matches_coordination(self, rule):
        tokens = [
            make_token(0, "rich", "rich", "ADJ", "JJ", "amod", 3),
            make_token(1, "and", "and", "CCONJ", "CC", "cc", 0),
            make_token(2, "complex", "complex", "ADJ", "JJ", "conj", 0),
            make_token(3, "body", "body", "NOUN", "NN", "ROOT", 3),
            make_token(4, "of", "of", "ADP", "IN", "prep", 3),
            make_token(5, "knowledge", "knowledge", "NOUN", "NN", "pobj", 4),
        ]
        deps = [(0, 3, "amod"), (1, 0, "cc"), (2, 0, "conj"), (4, 3, "prep"), (5, 4, "pobj")]
        tree = make_tree(tokens, deps)
        assert rule.matches(tree) is True

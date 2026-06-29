import pytest

from src.extractor.rules.temporal import TemporalRule
from tests.conftest import make_token, make_tree


class TestTemporalRule:
    @pytest.fixture
    def rule(self):
        return TemporalRule()

    def test_matches_temporal_marker(self, rule):
        tokens = [
            make_token(0, "Since", "since", "ADP", "IN", "mark", 4),
            make_token(1, "the", "the", "DET", "DT", "det", 2),
            make_token(2, "discovery", "discovery", "NOUN", "NN", "advcl", 4),
            make_token(3, "of", "of", "ADP", "IN", "prep", 2),
            make_token(4, "dopamine", "dopamine", "NOUN", "NN", "pobj", 3),
        ]
        deps = [(0, 2, "mark"), (1, 2, "det"), (3, 2, "prep"), (4, 3, "pobj")]
        tree = make_tree(tokens, deps)
        assert rule.matches(tree) is True

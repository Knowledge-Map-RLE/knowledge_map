import pytest

from src.extractor.rules.active_voice import ActiveVoiceRule
from tests.conftest import make_token, make_tree, make_context


class TestActiveVoiceRule:
    @pytest.fixture
    def rule(self):
        return ActiveVoiceRule()

    def test_matches_active_voice(self, rule):
        tokens = [
            make_token(0, "Genetic", "genetic", "ADJ", "JJ", "", 1),
            make_token(1, "factors", "factor", "NOUN", "NNS", "", 2),
            make_token(2, "influence", "influence", "VERB", "VBP", "", 2),
            make_token(3, "PD", "PD", "NOUN", "NN", "", 2),
        ]
        deps = [(0, 1, "amod"), (1, 2, "nsubj"), (3, 2, "obj")]
        tree = make_tree(tokens, deps)
        assert rule.matches(tree) is True

    def test_extract_active_voice(self, rule):
        tokens = [
            make_token(0, "Genetic", "genetic", "ADJ", "JJ", "", 1),
            make_token(1, "factors", "factor", "NOUN", "NNS", "", 2),
            make_token(2, "influence", "influence", "VERB", "VBP", "", 2),
            make_token(3, "PD", "PD", "NOUN", "NN", "", 2),
        ]
        deps = [(0, 1, "amod"), (1, 2, "nsubj"), (3, 2, "obj")]
        tree = make_tree(tokens, deps)
        statements = rule.extract(tree, make_context())
        assert len(statements) == 1
        assert statements[0].predicate == "influence"

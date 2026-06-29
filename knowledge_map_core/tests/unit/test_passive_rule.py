import pytest

from src.extractor.rules.passive_voice import PassiveVoiceRule
from tests.conftest import make_token, make_tree, make_context


class TestPassiveVoiceRule:
    @pytest.fixture
    def rule(self):
        return PassiveVoiceRule()

    def test_matches_passive(self, rule):
        tokens = [
            make_token(0, "Dopamine", "dopamine", "NOUN", "NN", "", 2),
            make_token(1, "was", "be", "AUX", "VBD", "", 2),
            make_token(2, "discovered", "discover", "VERB", "VBN", "", 2),
        ]
        deps = [(0, 2, "nsubj:pass"), (1, 2, "aux:pass")]
        tree = make_tree(tokens, deps)
        assert rule.matches(tree) is True

    def test_extract_passive_with_agent(self, rule):
        tokens = [
            make_token(0, "Dopamine", "dopamine", "NOUN", "NN", "", 2),
            make_token(1, "was", "be", "AUX", "VBD", "", 2),
            make_token(2, "discovered", "discover", "VERB", "VBN", "", 2),
            make_token(3, "by", "by", "ADP", "IN", "", 4),
            make_token(4, "researchers", "researcher", "NOUN", "NNS", "", 2),
        ]
        deps = [(0, 2, "nsubj:pass"), (1, 2, "aux:pass"), (3, 4, "case"), (4, 2, "obl")]
        tree = make_tree(tokens, deps)
        statements = rule.extract(tree, make_context())
        assert len(statements) >= 1

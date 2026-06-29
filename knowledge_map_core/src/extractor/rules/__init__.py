from src.extractor.rules.copular import CopularRule
from src.extractor.rules.copular_like import CopularLikeRule
from src.extractor.rules.passive_voice import PassiveVoiceRule
from src.extractor.rules.active_voice import ActiveVoiceRule
from src.extractor.rules.coordination import CoordinationRule
from src.extractor.rules.negation import NegationRule
from src.extractor.rules.causal import CausalRule
from src.extractor.rules.temporal import TemporalRule
from src.extractor.rules.relative_clause import RelativeClauseRule
from src.extractor.rules.as_role import AsRoleRule
from src.extractor.rules.such_as import SuchAsRule
from src.extractor.rules.multi_word_predicate import MultiWordPredicateRule
from src.extractor.rules.with_have import WithHaveRule
from src.extractor.rules.named import NamedRule
from src.extractor.rules.copular_remain import CopularRemainRule
from src.extractor.rules.adjective_preposition import AdjectivePrepositionRule
from src.extractor.rules.temporal_comparison import TemporalComparisonRule

__all__ = [
    "CopularRule",
    "CopularLikeRule",
    "PassiveVoiceRule",
    "ActiveVoiceRule",
    "CoordinationRule",
    "NegationRule",
    "CausalRule",
    "TemporalRule",
    "RelativeClauseRule",
    "AsRoleRule",
    "SuchAsRule",
    "MultiWordPredicateRule",
    "WithHaveRule",
    "NamedRule",
    "CopularRemainRule",
    "AdjectivePrepositionRule",
    "TemporalComparisonRule",
]

ALL_RULES = [
    CausalRule(),
    NegationRule(),
    PassiveVoiceRule(),
    CopularRule(),
    CopularLikeRule(),
    ActiveVoiceRule(),
    CoordinationRule(),
    TemporalRule(),
    RelativeClauseRule(),
    AsRoleRule(),
    SuchAsRule(),
    MultiWordPredicateRule(),
    WithHaveRule(),
    NamedRule(),
    CopularRemainRule(),
    AdjectivePrepositionRule(),
    TemporalComparisonRule(),
]

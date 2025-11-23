"""
Voting system for aggregating outputs from multiple NLP processors.
"""

from src.voting.voting_engine import VotingEngine
from src.voting.confidence_aggregator import ConfidenceAggregator
from src.voting.agreement_calculator import AgreementCalculator

__all__ = ['VotingEngine', 'ConfidenceAggregator', 'AgreementCalculator']

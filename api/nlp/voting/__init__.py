"""
Voting system for aggregating outputs from multiple NLP processors.
"""

from .voting_engine import VotingEngine
from .confidence_aggregator import ConfidenceAggregator
from .agreement_calculator import AgreementCalculator

__all__ = ['VotingEngine', 'ConfidenceAggregator', 'AgreementCalculator']

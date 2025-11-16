"""
Confidence aggregation strategies for voting system.

Combines confidence scores from multiple processors into a single score.
"""

from typing import List
import numpy as np


class ConfidenceAggregator:
    """
    Aggregates confidence scores using various strategies.
    """

    @staticmethod
    def aggregate_mean(confidences: List[float]) -> float:
        """
        Simple arithmetic mean of confidences.

        Args:
            confidences: List of confidence scores (0.0-1.0)

        Returns:
            Mean confidence
        """
        if not confidences:
            return 0.0
        return float(np.mean(confidences))

    @staticmethod
    def aggregate_weighted_mean(
        confidences: List[float],
        weights: List[float]
    ) -> float:
        """
        Weighted mean of confidences.

        Args:
            confidences: List of confidence scores
            weights: Processor weights (e.g., based on known accuracy)

        Returns:
            Weighted mean confidence
        """
        if not confidences or not weights:
            return 0.0

        if len(confidences) != len(weights):
            raise ValueError("Confidences and weights must have same length")

        return float(np.average(confidences, weights=weights))

    @staticmethod
    def aggregate_min(confidences: List[float]) -> float:
        """
        Conservative: use minimum confidence (pessimistic).

        Args:
            confidences: List of confidence scores

        Returns:
            Minimum confidence
        """
        if not confidences:
            return 0.0
        return float(min(confidences))

    @staticmethod
    def aggregate_max(confidences: List[float]) -> float:
        """
        Optimistic: use maximum confidence.

        Args:
            confidences: List of confidence scores

        Returns:
            Maximum confidence
        """
        if not confidences:
            return 0.0
        return float(max(confidences))

    @staticmethod
    def aggregate_harmonic_mean(confidences: List[float]) -> float:
        """
        Harmonic mean - penalizes low confidences more than arithmetic mean.

        Args:
            confidences: List of confidence scores

        Returns:
            Harmonic mean confidence
        """
        if not confidences:
            return 0.0

        # Filter out zeros to avoid division by zero
        non_zero = [c for c in confidences if c > 0]

        if not non_zero:
            return 0.0

        return float(len(non_zero) / sum(1.0 / c for c in non_zero))

    @staticmethod
    def aggregate_product(confidences: List[float]) -> float:
        """
        Product of confidences - assumes independence.

        Useful when all processors must be confident.

        Args:
            confidences: List of confidence scores

        Returns:
            Product of confidences
        """
        if not confidences:
            return 0.0

        return float(np.prod(confidences))

    @staticmethod
    def aggregate_noisy_or(confidences: List[float]) -> float:
        """
        Noisy-OR aggregation - at least one processor is confident.

        Formula: 1 - ∏(1 - c_i)

        Args:
            confidences: List of confidence scores

        Returns:
            Noisy-OR aggregated confidence
        """
        if not confidences:
            return 0.0

        return float(1.0 - np.prod([1.0 - c for c in confidences]))

    @staticmethod
    def aggregate_median(confidences: List[float]) -> float:
        """
        Median confidence - robust to outliers.

        Args:
            confidences: List of confidence scores

        Returns:
            Median confidence
        """
        if not confidences:
            return 0.0
        return float(np.median(confidences))

    @staticmethod
    def aggregate_trimmed_mean(
        confidences: List[float],
        trim_proportion: float = 0.1
    ) -> float:
        """
        Trimmed mean - removes top/bottom values before averaging.

        Args:
            confidences: List of confidence scores
            trim_proportion: Proportion to trim from each end (0.0-0.5)

        Returns:
            Trimmed mean confidence
        """
        if not confidences:
            return 0.0

        if trim_proportion < 0 or trim_proportion >= 0.5:
            raise ValueError("trim_proportion must be in [0, 0.5)")

        sorted_conf = sorted(confidences)
        n = len(sorted_conf)
        trim_count = int(n * trim_proportion)

        if trim_count > 0:
            trimmed = sorted_conf[trim_count:-trim_count]
        else:
            trimmed = sorted_conf

        if not trimmed:
            return 0.0

        return float(np.mean(trimmed))

    @staticmethod
    def aggregate_with_agreement_bonus(
        confidences: List[float],
        agreement_bonus: float = 0.1
    ) -> float:
        """
        Mean confidence with bonus for high agreement.

        The more processors agree, the higher the final confidence.

        Args:
            confidences: List of confidence scores
            agreement_bonus: Bonus per agreeing processor (default: 0.1)

        Returns:
            Confidence with agreement bonus
        """
        if not confidences:
            return 0.0

        base_confidence = float(np.mean(confidences))

        # Bonus based on number of agreeing processors
        num_processors = len(confidences)
        bonus = (num_processors - 1) * agreement_bonus

        # Cap at 1.0
        return min(1.0, base_confidence + bonus)

    def aggregate(
        self,
        confidences: List[float],
        strategy: str = 'mean',
        **kwargs
    ) -> float:
        """
        Aggregate confidences using specified strategy.

        Args:
            confidences: List of confidence scores
            strategy: Aggregation strategy name
            **kwargs: Additional arguments for specific strategies

        Returns:
            Aggregated confidence

        Supported strategies:
            - 'mean': arithmetic mean (default)
            - 'weighted_mean': weighted mean (requires 'weights' kwarg)
            - 'min': minimum (conservative)
            - 'max': maximum (optimistic)
            - 'harmonic_mean': harmonic mean
            - 'product': product of confidences
            - 'noisy_or': noisy-OR aggregation
            - 'median': median
            - 'trimmed_mean': trimmed mean (optional 'trim_proportion' kwarg)
            - 'agreement_bonus': mean with agreement bonus (optional 'agreement_bonus' kwarg)
        """
        strategy_map = {
            'mean': self.aggregate_mean,
            'weighted_mean': lambda c: self.aggregate_weighted_mean(c, kwargs.get('weights', [])),
            'min': self.aggregate_min,
            'max': self.aggregate_max,
            'harmonic_mean': self.aggregate_harmonic_mean,
            'product': self.aggregate_product,
            'noisy_or': self.aggregate_noisy_or,
            'median': self.aggregate_median,
            'trimmed_mean': lambda c: self.aggregate_trimmed_mean(
                c, kwargs.get('trim_proportion', 0.1)
            ),
            'agreement_bonus': lambda c: self.aggregate_with_agreement_bonus(
                c, kwargs.get('agreement_bonus', 0.1)
            ),
        }

        if strategy not in strategy_map:
            raise ValueError(f"Unknown aggregation strategy: {strategy}")

        return strategy_map[strategy](confidences)

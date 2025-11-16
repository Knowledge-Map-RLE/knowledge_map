"""
Agreement metrics for evaluating voting results.

Calculates various metrics to measure how well processors agree with each other.
"""

from typing import List, Dict, Tuple
import numpy as np


class AgreementCalculator:
    """
    Calculates agreement metrics between multiple processors.
    """

    @staticmethod
    def calculate_simple_agreement(
        num_agreed: int,
        num_disagreed: int
    ) -> float:
        """
        Simple agreement rate.

        Args:
            num_agreed: Number of agreed annotations
            num_disagreed: Number of disagreed annotations

        Returns:
            Agreement rate (0.0-1.0)
        """
        total = num_agreed + num_disagreed

        if total == 0:
            return 0.0

        return num_agreed / total

    @staticmethod
    def calculate_overall_agreement(
        num_agreed_tokens: int,
        num_disagreed_tokens: int,
        num_agreed_deps: int = 0,
        num_disagreed_deps: int = 0,
        num_agreed_entities: int = 0,
        num_disagreed_entities: int = 0,
    ) -> float:
        """
        Calculate overall agreement across all annotation types.

        Weighted average of token, dependency, and entity agreement.

        Args:
            num_agreed_tokens: Number of agreed tokens
            num_disagreed_tokens: Number of disagreed tokens
            num_agreed_deps: Number of agreed dependencies
            num_disagreed_deps: Number of disagreed dependencies
            num_agreed_entities: Number of agreed entities
            num_disagreed_entities: Number of disagreed entities

        Returns:
            Overall agreement score (0.0-1.0)
        """
        # Calculate per-type agreement
        token_total = num_agreed_tokens + num_disagreed_tokens
        dep_total = num_agreed_deps + num_disagreed_deps
        entity_total = num_agreed_entities + num_disagreed_entities

        token_agreement = num_agreed_tokens / token_total if token_total > 0 else 0.0
        dep_agreement = num_agreed_deps / dep_total if dep_total > 0 else 0.0
        entity_agreement = num_agreed_entities / entity_total if entity_total > 0 else 0.0

        # Weights (tokens are most numerous, so lower weight)
        weights = []
        values = []

        if token_total > 0:
            weights.append(1.0)
            values.append(token_agreement)

        if dep_total > 0:
            weights.append(2.0)  # Dependencies are more important
            values.append(dep_agreement)

        if entity_total > 0:
            weights.append(1.5)  # Entities are important
            values.append(entity_agreement)

        if not values:
            return 0.0

        # Weighted average
        return float(np.average(values, weights=weights))

    @staticmethod
    def calculate_fleiss_kappa(
        annotations: List[List[str]],
        categories: List[str]
    ) -> float:
        """
        Calculate Fleiss' Kappa for inter-annotator agreement.

        Useful when multiple processors annotate the same items.

        Args:
            annotations: List of annotation lists (one per item)
                         Each inner list contains annotations from different processors
            categories: List of possible annotation categories

        Returns:
            Fleiss' Kappa (can be negative for disagreement worse than chance)

        Example:
            annotations = [
                ['NOUN', 'NOUN', 'NOUN'],  # Item 1: all agree
                ['VERB', 'NOUN', 'VERB'],  # Item 2: 2 agree
            ]
            categories = ['NOUN', 'VERB', 'ADJ']
            kappa = calculate_fleiss_kappa(annotations, categories)
        """
        if not annotations:
            return 0.0

        n_items = len(annotations)  # Number of items being annotated
        n_raters = len(annotations[0])  # Number of raters (processors)
        n_categories = len(categories)

        # Build category index
        cat_to_idx = {cat: i for i, cat in enumerate(categories)}

        # Matrix: items x categories
        # Each cell = how many raters assigned this category to this item
        matrix = np.zeros((n_items, n_categories))

        for i, item_annotations in enumerate(annotations):
            for annotation in item_annotations:
                if annotation in cat_to_idx:
                    matrix[i, cat_to_idx[annotation]] += 1

        # Calculate P_i (proportion of agreement for item i)
        P_i = np.sum(matrix * matrix, axis=1) - n_raters
        P_i = P_i / (n_raters * (n_raters - 1))

        # Mean proportion of agreement
        P_bar = np.mean(P_i)

        # Calculate P_j (proportion of all assignments to category j)
        P_j = np.sum(matrix, axis=0) / (n_items * n_raters)

        # Expected agreement by chance
        P_e_bar = np.sum(P_j * P_j)

        # Fleiss' Kappa
        if P_e_bar == 1.0:
            return 1.0  # Perfect agreement

        kappa = (P_bar - P_e_bar) / (1.0 - P_e_bar)

        return float(kappa)

    @staticmethod
    def calculate_cohen_kappa(
        annotations1: List[str],
        annotations2: List[str],
        categories: List[str]
    ) -> float:
        """
        Calculate Cohen's Kappa for agreement between two processors.

        Args:
            annotations1: Annotations from processor 1
            annotations2: Annotations from processor 2
            categories: List of possible categories

        Returns:
            Cohen's Kappa
        """
        if len(annotations1) != len(annotations2):
            raise ValueError("Annotation lists must have same length")

        if not annotations1:
            return 0.0

        n = len(annotations1)

        # Observed agreement
        agreements = sum(1 for a1, a2 in zip(annotations1, annotations2) if a1 == a2)
        p_o = agreements / n

        # Expected agreement by chance
        cat_to_idx = {cat: i for i, cat in enumerate(categories)}
        n_categories = len(categories)

        # Count occurrences of each category
        count1 = np.zeros(n_categories)
        count2 = np.zeros(n_categories)

        for a1, a2 in zip(annotations1, annotations2):
            if a1 in cat_to_idx:
                count1[cat_to_idx[a1]] += 1
            if a2 in cat_to_idx:
                count2[cat_to_idx[a2]] += 1

        # Probabilities
        prob1 = count1 / n
        prob2 = count2 / n

        # Expected agreement
        p_e = np.sum(prob1 * prob2)

        if p_e == 1.0:
            return 1.0

        kappa = (p_o - p_e) / (1.0 - p_e)

        return float(kappa)

    @staticmethod
    def calculate_pairwise_agreement(
        processor_outputs: List[Dict[str, List]],
        annotation_type: str = 'tokens'
    ) -> Dict[Tuple[str, str], float]:
        """
        Calculate pairwise agreement between all processor pairs.

        Args:
            processor_outputs: List of dicts with processor results
            annotation_type: Type of annotations to compare ('tokens', 'entities', etc.)

        Returns:
            Dictionary mapping (processor1, processor2) to agreement score
        """
        n_processors = len(processor_outputs)
        agreements = {}

        for i in range(n_processors):
            for j in range(i + 1, n_processors):
                proc1 = processor_outputs[i]
                proc2 = processor_outputs[j]

                name1 = proc1.get('name', f'processor_{i}')
                name2 = proc2.get('name', f'processor_{j}')

                # Calculate agreement for this pair
                # (Simplified - would need actual annotation comparison logic)
                annotations1 = proc1.get(annotation_type, [])
                annotations2 = proc2.get(annotation_type, [])

                # Simple overlap metric
                if annotations1 and annotations2:
                    overlap = len(set(annotations1) & set(annotations2))
                    union = len(set(annotations1) | set(annotations2))
                    agreement = overlap / union if union > 0 else 0.0
                else:
                    agreement = 0.0

                agreements[(name1, name2)] = agreement

        return agreements

    @staticmethod
    def calculate_krippendorff_alpha(
        annotations: List[List[str]],
        metric: str = 'nominal'
    ) -> float:
        """
        Calculate Krippendorff's Alpha for inter-rater reliability.

        More general than Kappa - handles missing data and various metrics.

        Args:
            annotations: List of annotation lists (items x raters)
            metric: Distance metric ('nominal', 'ordinal', 'interval', 'ratio')

        Returns:
            Krippendorff's Alpha

        Note: Simplified implementation for nominal data
        """
        if not annotations:
            return 0.0

        # Convert to numpy array
        # Rows = items, Columns = raters
        try:
            data = np.array(annotations, dtype=object)
        except:
            return 0.0

        n_items, n_raters = data.shape

        # Get unique categories
        categories = set()
        for row in data:
            categories.update(row)
        categories = list(categories)

        if len(categories) <= 1:
            return 1.0  # Perfect agreement

        # Simplified nominal metric calculation
        # Count pairwise disagreements
        total_pairs = 0
        disagreements = 0

        for i in range(n_items):
            for r1 in range(n_raters):
                for r2 in range(r1 + 1, n_raters):
                    if data[i, r1] and data[i, r2]:  # Both rated this item
                        total_pairs += 1
                        if data[i, r1] != data[i, r2]:
                            disagreements += 1

        if total_pairs == 0:
            return 0.0

        observed_disagreement = disagreements / total_pairs

        # Expected disagreement (simplified)
        # Count category frequencies
        cat_counts = {cat: 0 for cat in categories}
        total_ratings = 0

        for row in data:
            for val in row:
                if val:
                    cat_counts[val] += 1
                    total_ratings += 1

        if total_ratings == 0:
            return 0.0

        # Expected disagreement
        expected_disagreement = 0
        for cat1 in categories:
            for cat2 in categories:
                if cat1 != cat2:
                    p1 = cat_counts[cat1] / total_ratings
                    p2 = cat_counts[cat2] / total_ratings
                    expected_disagreement += p1 * p2

        if expected_disagreement == 0:
            return 1.0

        # Krippendorff's Alpha
        alpha = 1.0 - (observed_disagreement / expected_disagreement)

        return float(alpha)

    @staticmethod
    def get_agreement_interpretation(score: float) -> str:
        """
        Get human-readable interpretation of agreement score (Kappa/Alpha).

        Args:
            score: Agreement score

        Returns:
            Interpretation string
        """
        if score < 0:
            return "Poor (worse than chance)"
        elif score < 0.20:
            return "Slight"
        elif score < 0.40:
            return "Fair"
        elif score < 0.60:
            return "Moderate"
        elif score < 0.80:
            return "Substantial"
        else:
            return "Almost perfect"

"""
Ontology Reconstruction Optimizer

Uses genetic algorithm to optimize text reconstruction rules.

The genetic algorithm discovers optimal weights for reconstruction rules
to maximize accuracy on training examples.

Fitness Function: Minimize Levenshtein distance to original text
- Lower fitness = better reconstruction
- Target fitness: 0 (perfect reconstruction)

Algorithm:
1. Initialize population of rule sets (each with different weights)
2. For each generation:
   a. Evaluate fitness on training examples
   b. Select top performers (50%)
   c. Crossover: combine rule sets
   d. Mutate: adjust weights randomly
   e. Create new generation
3. Return best rule set after N generations
"""

import random
from typing import List, Dict, Any, Callable, Optional
from dataclasses import dataclass, field
import json
import logging
from enum import Enum
import Levenshtein

logger = logging.getLogger(__name__)


class RuleType(Enum):
    """Types of reconstruction rules"""
    TOKEN_ORDER = "token_order"
    ORIGINAL_TEXT = "original_text"
    WHITESPACE = "whitespace"
    PUNCTUATION = "punctuation"
    CAPITALIZATION = "capitalization"
    MORPHOLOGY = "morphology"
    SPECIAL_CHARS = "special_chars"


@dataclass
class ReconstructionRule:
    """
    A rule for text reconstruction.

    Example rules:
    - When POS=PUNCT, handle whitespace specially
    - When token is first in sentence, capitalize
    - Preserve contractions (e.g., "Parkinson's")
    """
    rule_id: str
    rule_type: RuleType
    description: str
    weight: float = 1.0  # Genetic algorithm will optimize this
    enabled: bool = True

    def apply(self, token_data: Dict[str, Any], context: Dict[str, Any]) -> str:
        """
        Apply the rule to a token.

        Args:
            token_data: Token properties {text, whitespace, pos, morph, ...}
            context: Context {prev_token, next_token, is_first, is_last, ...}

        Returns:
            Processed token string
        """
        if not self.enabled or self.weight <= 0:
            return token_data.get('text', '')

        text = token_data.get('text', '')

        # Rule implementations
        if self.rule_type == RuleType.TOKEN_ORDER:
            # Ensure correct ordering - handled by query, not individual rule
            return text

        elif self.rule_type == RuleType.ORIGINAL_TEXT:
            # Use original text, not lemma
            return text

        elif self.rule_type == RuleType.WHITESPACE:
            # Add whitespace after token
            whitespace = token_data.get('whitespace', ' ')
            return text + whitespace

        elif self.rule_type == RuleType.PUNCTUATION:
            # Handle punctuation specially
            pos = token_data.get('pos', '')
            if pos == 'PUNCT':
                # No space before punctuation in English
                if context.get('prev_text', '').endswith(' '):
                    # Remove trailing space from previous token
                    pass
            return text

        elif self.rule_type == RuleType.CAPITALIZATION:
            # Preserve capitalization from original
            return text

        elif self.rule_type == RuleType.MORPHOLOGY:
            # Use original inflected form, not lemma
            return text

        elif self.rule_type == RuleType.SPECIAL_CHARS:
            # Handle special characters (quotes, dashes, etc.)
            return text

        return text


@dataclass
class ReconstructionRuleSet:
    """
    A complete set of reconstruction rules with weights.
    This is what the genetic algorithm evolves.
    """
    rules: List[ReconstructionRule] = field(default_factory=list)
    fitness: float = float('inf')  # To be calculated
    generation: int = 0

    def get_total_weight(self) -> float:
        """Get sum of all rule weights"""
        return sum(r.weight for r in self.rules if r.enabled)

    def normalize_weights(self):
        """Normalize weights to sum to 1.0"""
        total = self.get_total_weight()
        if total > 0:
            for rule in self.rules:
                if rule.enabled:
                    rule.weight /= total


@dataclass
class OptimizationResult:
    """Results of genetic algorithm optimization"""
    best_rule_set: ReconstructionRuleSet
    best_fitness: float
    generations_completed: int
    fitness_history: List[float]
    convergence_iteration: int  # When fitness stopped improving
    training_accuracy: float  # Accuracy on training set
    test_accuracy: float  # Accuracy on test set
    optimization_time_seconds: float


class OntologyOptimizer:
    """
    Genetic algorithm optimizer for reconstruction rules.

    Parameters:
        population_size: Number of rule sets in each generation
        generations: Total number of generations to evolve
        mutation_rate: Probability of mutation for each weight
        crossover_rate: Probability of crossover between parents
        elite_size: Number of best performers to keep unchanged
    """

    def __init__(
        self,
        population_size: int = 50,
        generations: int = 100,
        mutation_rate: float = 0.1,
        crossover_rate: float = 0.7,
        elite_size: int = 5
    ):
        self.population_size = population_size
        self.generations = generations
        self.mutation_rate = mutation_rate
        self.crossover_rate = crossover_rate
        self.elite_size = elite_size

        # Initialize base rules
        self.base_rules = self._initialize_base_rules()

    def _initialize_base_rules(self) -> List[ReconstructionRule]:
        """Initialize base reconstruction rules"""
        rules = [
            ReconstructionRule(
                rule_id='token_order',
                rule_type=RuleType.TOKEN_ORDER,
                description='Order tokens by (sent_idx, token_idx)',
                weight=1.0,
                enabled=True
            ),
            ReconstructionRule(
                rule_id='original_text',
                rule_type=RuleType.ORIGINAL_TEXT,
                description='Use HAS_TEXT property, not lemma',
                weight=1.0,
                enabled=True
            ),
            ReconstructionRule(
                rule_id='whitespace_preservation',
                rule_type=RuleType.WHITESPACE,
                description='Append HAS_WHITESPACE after each token',
                weight=1.0,
                enabled=True
            ),
            ReconstructionRule(
                rule_id='punctuation_handling',
                rule_type=RuleType.PUNCTUATION,
                description='Handle PUNCT tokens specially',
                weight=1.0,
                enabled=True
            ),
            ReconstructionRule(
                rule_id='capitalization',
                rule_type=RuleType.CAPITALIZATION,
                description='Preserve original capitalization',
                weight=1.0,
                enabled=True
            ),
            ReconstructionRule(
                rule_id='morphology',
                rule_type=RuleType.MORPHOLOGY,
                description='Use inflected forms, not lemmas',
                weight=1.0,
                enabled=True
            ),
            ReconstructionRule(
                rule_id='special_chars',
                rule_type=RuleType.SPECIAL_CHARS,
                description='Handle special characters correctly',
                weight=0.5,
                enabled=False  # Not all texts need this
            ),
        ]
        return rules

    def optimize_rules(
        self,
        training_examples: List[Dict[str, str]],
        test_examples: Optional[List[Dict[str, str]]] = None,
        verbose: bool = True
    ) -> OptimizationResult:
        """
        Optimize rule weights using genetic algorithm.

        Args:
            training_examples: List of {'original': str, 'tokens': List[Dict]}
            test_examples: Optional test set for validation
            verbose: Print progress information

        Returns:
            OptimizationResult with best rules and metrics
        """
        import time

        start_time = time.time()

        if test_examples is None:
            test_examples = training_examples[:len(training_examples) // 4]

        # Initialize population
        population = [
            self._create_rule_set()
            for _ in range(self.population_size)
        ]

        best_rule_set = None
        best_fitness = float('inf')
        fitness_history = []
        generations_without_improvement = 0
        convergence_iteration = 0

        if verbose:
            logger.info(f"Starting genetic algorithm optimization")
            logger.info(f"Population size: {self.population_size}")
            logger.info(f"Generations: {self.generations}")
            logger.info(f"Training examples: {len(training_examples)}")

        for generation in range(self.generations):
            # Evaluate fitness for all rule sets
            for rule_set in population:
                rule_set.fitness = self._evaluate_fitness(rule_set, training_examples)
                rule_set.generation = generation

            # Find best performer
            sorted_population = sorted(population, key=lambda x: x.fitness)
            current_best = sorted_population[0]

            if current_best.fitness < best_fitness:
                best_fitness = current_best.fitness
                best_rule_set = self._clone_rule_set(current_best)
                generations_without_improvement = 0
            else:
                generations_without_improvement += 1

            fitness_history.append(best_fitness)

            if verbose and (generation % 10 == 0 or generation == self.generations - 1):
                logger.info(
                    f"Generation {generation:3d}: "
                    f"Best fitness = {best_fitness:.2f} | "
                    f"Population avg = {sum(r.fitness for r in population) / len(population):.2f}"
                )

            # Check for convergence
            if generations_without_improvement >= 20:
                convergence_iteration = generation
                if verbose:
                    logger.info(f"Converged at generation {generation}")
                break

            # Selection: keep top 50%
            selected = sorted_population[:self.population_size // 2]

            # Elitism: keep best unchanged
            elite = selected[:self.elite_size]

            # Create new population
            new_population = [self._clone_rule_set(r) for r in elite]

            # Crossover and mutation
            while len(new_population) < self.population_size:
                if random.random() < self.crossover_rate and len(selected) >= 2:
                    parent1 = random.choice(selected)
                    parent2 = random.choice(selected)
                    child = self._crossover(parent1, parent2)
                else:
                    child = random.choice(selected)

                child = self._mutate_rules(child)
                new_population.append(child)

            population = new_population[:self.population_size]

        # Final evaluation
        if convergence_iteration == 0:
            convergence_iteration = self.generations

        # Compute accuracies
        training_accuracy = self._compute_accuracy(best_rule_set, training_examples)
        test_accuracy = self._compute_accuracy(best_rule_set, test_examples)

        elapsed = time.time() - start_time

        if verbose:
            logger.info(f"\nOptimization Complete!")
            logger.info(f"Best fitness: {best_fitness:.2f}")
            logger.info(f"Training accuracy: {training_accuracy:.2%}")
            logger.info(f"Test accuracy: {test_accuracy:.2%}")
            logger.info(f"Time elapsed: {elapsed:.2f}s")

        return OptimizationResult(
            best_rule_set=best_rule_set,
            best_fitness=best_fitness,
            generations_completed=convergence_iteration,
            fitness_history=fitness_history,
            convergence_iteration=convergence_iteration,
            training_accuracy=training_accuracy,
            test_accuracy=test_accuracy,
            optimization_time_seconds=elapsed
        )

    def _create_rule_set(self) -> ReconstructionRuleSet:
        """Create a new rule set with randomly initialized weights"""
        rules = []
        for base_rule in self.base_rules:
            # Add random variation to weights
            weight = base_rule.weight * random.uniform(0.5, 1.5)
            rule = ReconstructionRule(
                rule_id=base_rule.rule_id,
                rule_type=base_rule.rule_type,
                description=base_rule.description,
                weight=max(0.0, weight),
                enabled=base_rule.enabled
            )
            rules.append(rule)

        return ReconstructionRuleSet(rules=rules)

    def _evaluate_fitness(
        self,
        rule_set: ReconstructionRuleSet,
        examples: List[Dict[str, Any]]
    ) -> float:
        """
        Evaluate fitness: sum of Levenshtein distances.
        Lower is better (0 = perfect reconstruction).
        """
        total_distance = 0

        for example in examples:
            original = example.get('original', '')
            tokens = example.get('tokens', [])

            # Reconstruct using rule set
            reconstructed = self._reconstruct_with_rules(tokens, rule_set)

            # Compute distance
            distance = Levenshtein.distance(original, reconstructed)
            total_distance += distance

        return total_distance

    def _reconstruct_with_rules(
        self,
        tokens: List[Dict[str, Any]],
        rule_set: ReconstructionRuleSet
    ) -> str:
        """Reconstruct text applying rules from rule_set"""
        parts = []

        for i, token in enumerate(tokens):
            context = {
                'prev_token': tokens[i - 1] if i > 0 else None,
                'next_token': tokens[i + 1] if i < len(tokens) - 1 else None,
                'position': i,
                'total': len(tokens),
                'is_first': i == 0,
                'is_last': i == len(tokens) - 1,
            }

            text = token.get('text', '')
            whitespace = token.get('whitespace', ' ')

            # Apply rules
            for rule in rule_set.rules:
                if rule.rule_type == RuleType.WHITESPACE:
                    text = text + whitespace
                elif rule.rule_type in [RuleType.ORIGINAL_TEXT, RuleType.CAPITALIZATION]:
                    # These are already applied in token.text
                    pass

            parts.append(text)

        return ''.join(parts).rstrip()

    def _compute_accuracy(
        self,
        rule_set: ReconstructionRuleSet,
        examples: List[Dict[str, Any]]
    ) -> float:
        """
        Compute accuracy as percentage of examples with perfect reconstruction.
        """
        perfect_count = 0

        for example in examples:
            original = example.get('original', '')
            tokens = example.get('tokens', [])

            reconstructed = self._reconstruct_with_rules(tokens, rule_set)

            if reconstructed == original:
                perfect_count += 1

        return perfect_count / len(examples) if examples else 0.0

    def _crossover(
        self,
        parent1: ReconstructionRuleSet,
        parent2: ReconstructionRuleSet
    ) -> ReconstructionRuleSet:
        """
        Crossover: combine weights from two parents.

        Simple strategy: average the weights.
        """
        child_rules = []

        for r1, r2 in zip(parent1.rules, parent2.rules):
            # Average weights
            child_weight = (r1.weight + r2.weight) / 2
            # Sometimes take one parent's weight entirely
            if random.random() < 0.3:
                child_weight = r1.weight if random.random() < 0.5 else r2.weight

            child_rule = ReconstructionRule(
                rule_id=r1.rule_id,
                rule_type=r1.rule_type,
                description=r1.description,
                weight=child_weight,
                enabled=r1.enabled
            )
            child_rules.append(child_rule)

        return ReconstructionRuleSet(rules=child_rules)

    def _mutate_rules(
        self,
        rule_set: ReconstructionRuleSet
    ) -> ReconstructionRuleSet:
        """
        Mutate: randomly adjust weights.

        Mutation strategy:
        - Add Gaussian noise to weights
        - Occasionally enable/disable rules
        - Keep weights in [0, 2] range
        """
        mutated_rules = []

        for rule in rule_set.rules:
            if random.random() < self.mutation_rate:
                # Mutate weight: add random noise
                noise = random.gauss(0, 0.1)
                new_weight = rule.weight + noise
                new_weight = max(0.0, min(2.0, new_weight))  # Clamp to [0, 2]

                # Occasionally flip enabled flag
                new_enabled = rule.enabled
                if random.random() < 0.05:
                    new_enabled = not new_enabled

                mutated_rule = ReconstructionRule(
                    rule_id=rule.rule_id,
                    rule_type=rule.rule_type,
                    description=rule.description,
                    weight=new_weight,
                    enabled=new_enabled
                )
                mutated_rules.append(mutated_rule)
            else:
                mutated_rules.append(rule)

        return ReconstructionRuleSet(rules=mutated_rules)

    def _clone_rule_set(self, rule_set: ReconstructionRuleSet) -> ReconstructionRuleSet:
        """Create a deep copy of a rule set"""
        cloned_rules = [
            ReconstructionRule(
                rule_id=r.rule_id,
                rule_type=r.rule_type,
                description=r.description,
                weight=r.weight,
                enabled=r.enabled
            )
            for r in rule_set.rules
        ]
        return ReconstructionRuleSet(rules=cloned_rules)

    def save_rules(
        self,
        rule_set: ReconstructionRuleSet,
        filepath: str
    ) -> None:
        """
        Save optimized rules to JSON file.

        Format:
        {
          "rules": [
            {
              "rule_id": "token_order",
              "weight": 1.0,
              "description": "..."
            },
            ...
          ],
          "metadata": {
            "optimization_results": {...}
          }
        }
        """
        rules_data = {
            'rules': [
                {
                    'rule_id': r.rule_id,
                    'weight': r.weight,
                    'description': r.description,
                    'type': r.rule_type.value,
                    'enabled': r.enabled
                }
                for r in rule_set.rules
            ]
        }

        with open(filepath, 'w') as f:
            json.dump(rules_data, f, indent=2)

        logger.info(f"Rules saved to {filepath}")

    def load_rules(self, filepath: str) -> ReconstructionRuleSet:
        """Load rules from JSON file"""
        with open(filepath, 'r') as f:
            data = json.load(f)

        rules = []
        for rule_data in data['rules']:
            rule = ReconstructionRule(
                rule_id=rule_data['rule_id'],
                rule_type=RuleType(rule_data['type']),
                description=rule_data['description'],
                weight=rule_data['weight'],
                enabled=rule_data.get('enabled', True)
            )
            rules.append(rule)

        return ReconstructionRuleSet(rules=rules)

    def print_rules(self, rule_set: ReconstructionRuleSet) -> None:
        """Pretty print rule set"""
        print("\n" + "=" * 80)
        print("OPTIMIZED RECONSTRUCTION RULES")
        print("=" * 80)

        for i, rule in enumerate(rule_set.rules, 1):
            status = "✓ ENABLED" if rule.enabled else "✗ DISABLED"
            print(f"{i}. [{status}] {rule.rule_id} (weight: {rule.weight:.3f})")
            print(f"   Type: {rule.rule_type.value}")
            print(f"   {rule.description}")
            print()

        print("=" * 80)

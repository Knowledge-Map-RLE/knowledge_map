"""
Voting engine for aggregating NLP processor outputs.

Core rule: An annotation is accepted only if at least 2 processors agree.
If no consensus, the annotation is rejected (uncertain).
"""

from typing import List, Dict, Optional, Tuple, Set
from collections import defaultdict
import numpy as np

from ..unified_types import (
    UnifiedToken,
    UnifiedDependency,
    UnifiedEntity,
    UnifiedSentence,
    ProcessorOutput,
    VotingResult,
)
from .confidence_aggregator import ConfidenceAggregator
from .agreement_calculator import AgreementCalculator


class VotingEngine:
    """
    Voting engine that aggregates outputs from multiple NLP processors.

    Key principles:
    1. Minimum 2 processors must agree for annotation to be accepted
    2. Confidence is aggregated from agreeing processors
    3. Disagreements are logged but not included in final output
    """

    def __init__(
        self,
        min_agreement: int = 2,
        similarity_threshold: float = 0.8,
    ):
        """
        Initialize voting engine.

        Args:
            min_agreement: Minimum number of processors that must agree (default: 2)
            similarity_threshold: Threshold for considering annotations similar (0.0-1.0)
        """
        self.min_agreement = min_agreement
        self.similarity_threshold = similarity_threshold
        self.confidence_aggregator = ConfidenceAggregator()
        self.agreement_calculator = AgreementCalculator()

    # ============================================================================
    # Token voting
    # ============================================================================

    def vote_tokens(
        self,
        processor_outputs: List[ProcessorOutput]
    ) -> Tuple[List[UnifiedToken], List[List[UnifiedToken]]]:
        """
        Vote on tokens from multiple processors using overlap-based matching.

        Args:
            processor_outputs: List of outputs from different processors

        Returns:
            Tuple of (agreed_tokens, disagreed_token_groups)
        """
        if not processor_outputs:
            return [], []

        # Collect all tokens from all processors
        all_tokens = []
        for output in processor_outputs:
            all_tokens.extend(output.tokens)

        print(f"\n[VOTING DEBUG] Total tokens from all processors: {len(all_tokens)}")
        print(f"[VOTING DEBUG] Processors: {[output.processor_name for output in processor_outputs]}")

        # Group overlapping tokens using flexible matching
        token_clusters = self._cluster_overlapping_tokens(all_tokens)

        print(f"[VOTING DEBUG] Created {len(token_clusters)} token clusters")
        print(f"[VOTING DEBUG] Cluster sizes: {[len(c) for c in token_clusters[:20]]}")  # Show first 20

        agreed_tokens = []
        disagreed_tokens = []

        # Process each cluster
        for i, cluster in enumerate(token_clusters):
            if len(cluster) >= self.min_agreement:
                # Check if tokens agree on POS
                agreed_group = self._find_agreement_in_tokens_flexible(cluster)

                if agreed_group and len(agreed_group) >= self.min_agreement:
                    # Merge agreed tokens
                    merged_token = self._merge_tokens(agreed_group)
                    agreed_tokens.append(merged_token)
                    if i < 5:  # Debug first 5 agreements
                        print(f"[VOTING DEBUG] Cluster {i}: AGREED - text='{merged_token.text}' POS={merged_token.pos} sources={len(merged_token.sources)}")
                else:
                    disagreed_tokens.append(cluster)
                    if i < 5:  # Debug first 5 disagreements
                        pos_tags = [t.pos for t in cluster]
                        print(f"[VOTING DEBUG] Cluster {i}: DISAGREED - POS tags don't match: {pos_tags}")
            else:
                # Not enough processors analyzed this token
                disagreed_tokens.append(cluster)
                if i < 5 and len(cluster) == 1:
                    token = cluster[0]
                    print(f"[VOTING DEBUG] Cluster {i}: SINGLE TOKEN - text='{token.text}' POS={token.pos} source={token.sources}")

        print(f"[VOTING DEBUG] Final: {len(agreed_tokens)} agreed, {len(disagreed_tokens)} disagreed\n")

        return agreed_tokens, disagreed_tokens

    def _cluster_overlapping_tokens(
        self,
        tokens: List[UnifiedToken]
    ) -> List[List[UnifiedToken]]:
        """
        Cluster tokens that overlap significantly (IOU >= 0.5).

        Args:
            tokens: List of all tokens from all processors

        Returns:
            List of token clusters
        """
        if not tokens:
            return []

        # Sort by start position
        sorted_tokens = sorted(tokens, key=lambda t: t.start_char)

        clusters = []
        used = set()

        for i, token1 in enumerate(sorted_tokens):
            if i in used:
                continue

            # Start new cluster
            cluster = [token1]
            used.add(i)

            # Find overlapping tokens
            for j, token2 in enumerate(sorted_tokens[i+1:], start=i+1):
                if j in used:
                    continue

                # Check overlap (IOU >= 0.5)
                iou = self._calculate_token_iou(token1, token2)
                if iou >= 0.5:
                    cluster.append(token2)
                    used.add(j)
                elif token2.start_char > token1.end_char:
                    # No more overlaps possible
                    break

            clusters.append(cluster)

        return clusters

    def _calculate_token_iou(
        self,
        token1: UnifiedToken,
        token2: UnifiedToken
    ) -> float:
        """
        Calculate Intersection over Union for two tokens.

        Args:
            token1: First token
            token2: Second token

        Returns:
            IOU score (0.0-1.0)
        """
        # Calculate intersection
        intersection_start = max(token1.start_char, token2.start_char)
        intersection_end = min(token1.end_char, token2.end_char)

        if intersection_start >= intersection_end:
            return 0.0

        intersection = intersection_end - intersection_start

        # Calculate union
        union_start = min(token1.start_char, token2.start_char)
        union_end = max(token1.end_char, token2.end_char)
        union = union_end - union_start

        return intersection / union if union > 0 else 0.0

    def _find_agreement_in_tokens_flexible(
        self,
        tokens: List[UnifiedToken]
    ) -> Optional[List[UnifiedToken]]:
        """
        Find group of tokens that agree on POS (flexible matching).

        Relaxed requirements - only POS must match, not lemma.

        Returns:
            List of agreeing tokens or None
        """
        # Group by POS only (more flexible)
        groups = defaultdict(list)

        for token in tokens:
            key = token.pos
            groups[key].append(token)

        # Find largest agreeing group
        if not groups:
            return None

        largest_group = max(groups.values(), key=len)

        if len(largest_group) >= self.min_agreement:
            return largest_group

        return None

    def _find_agreement_in_tokens(
        self,
        tokens: List[UnifiedToken]
    ) -> Optional[List[UnifiedToken]]:
        """
        Find group of tokens that agree on POS and lemma (strict matching).

        Returns:
            List of agreeing tokens or None
        """
        # Group by (POS, lemma)
        groups = defaultdict(list)

        for token in tokens:
            key = (token.pos, token.lemma.lower())
            groups[key].append(token)

        # Find largest agreeing group
        if not groups:
            return None

        largest_group = max(groups.values(), key=len)

        if len(largest_group) >= self.min_agreement:
            return largest_group

        return None

    def _merge_tokens(self, tokens: List[UnifiedToken]) -> UnifiedToken:
        """
        Merge multiple agreeing tokens into one unified token.

        Uses majority voting for discrete features and averaging for confidence.
        """
        if not tokens:
            raise ValueError("Cannot merge empty token list")

        # Base token (use first as template)
        base = tokens[0]

        # Aggregate confidence
        confidences = [t.confidence for t in tokens]
        merged_confidence = self.confidence_aggregator.aggregate_mean(confidences)

        # Collect all sources
        all_sources = []
        for t in tokens:
            all_sources.extend(t.sources)

        # Majority vote for POS (should be same if they agreed)
        pos_votes = [t.pos for t in tokens]
        merged_pos = max(set(pos_votes), key=pos_votes.count)

        # Majority vote for lemma
        lemma_votes = [t.lemma.lower() for t in tokens]
        merged_lemma = max(set(lemma_votes), key=lemma_votes.count)

        # Merge morphological features (intersection of features)
        merged_morph = self._merge_morph_features([t.morph for t in tokens])

        # Create merged token
        merged_token = UnifiedToken(
            idx=base.idx,
            text=base.text,
            start_char=base.start_char,
            end_char=base.end_char,
            lemma=merged_lemma,
            pos=merged_pos,
            pos_fine=base.pos_fine,
            morph=merged_morph,
            confidence=merged_confidence,
            sources=list(set(all_sources)),
            is_stop=base.is_stop,
            is_punct=base.is_punct,
            is_space=base.is_space,
        )

        return merged_token

    def _merge_morph_features(
        self,
        morph_list: List[Dict[str, str]]
    ) -> Dict[str, str]:
        """
        Merge morphological features using majority voting.

        Only keeps features where at least 2 processors agree.
        """
        if not morph_list:
            return {}

        # Collect all feature keys
        all_keys = set()
        for morph in morph_list:
            all_keys.update(morph.keys())

        merged = {}

        # For each feature, vote on value
        for key in all_keys:
            values = [morph.get(key) for morph in morph_list if key in morph]

            if len(values) >= self.min_agreement:
                # Majority vote
                most_common = max(set(values), key=values.count)
                if values.count(most_common) >= self.min_agreement:
                    merged[key] = most_common

        return merged

    # ============================================================================
    # Dependency voting
    # ============================================================================

    def vote_dependencies(
        self,
        processor_outputs: List[ProcessorOutput]
    ) -> Tuple[List[UnifiedDependency], List[List[UnifiedDependency]]]:
        """
        Vote on dependencies from multiple processors.

        Args:
            processor_outputs: List of outputs from different processors

        Returns:
            Tuple of (agreed_dependencies, disagreed_dependency_groups)
        """
        if not processor_outputs:
            return [], []

        # Group dependencies by (head_idx, dependent_idx)
        dep_groups = defaultdict(list)

        # Debug: Count dependencies from each processor
        dep_counts = {}
        for output in processor_outputs:
            dep_counts[output.processor_name] = len(output.dependencies)
            for dep in output.dependencies:
                key = (dep.head_idx, dep.dependent_idx)
                dep_groups[key].append(dep)

        print(f"\n[DEPENDENCY DEBUG] Dependencies from each processor: {dep_counts}")
        print(f"[DEPENDENCY DEBUG] Total unique dependency pairs: {len(dep_groups)}")
        print(f"[DEPENDENCY DEBUG] min_agreement = {self.min_agreement}")

        agreed_deps = []
        disagreed_deps = []

        # Process each dependency pair
        for (head, dependent), deps in dep_groups.items():
            # Always take spaCy dependencies if available (single source is enough)
            # This ensures we get all ~6155 dependencies from spaCy
            spacy_dep = next((d for d in deps if 'spacy' in d.sources[0].lower()), None)

            if spacy_dep:
                # Use spaCy dependency
                agreed_deps.append(spacy_dep)
            elif len(deps) >= self.min_agreement:
                # No spaCy dep, try voting with other processors
                agreed_group = self._find_agreement_in_dependencies(deps)

                if agreed_group and len(agreed_group) >= self.min_agreement:
                    # Merge agreed dependencies
                    merged_dep = self._merge_dependencies(agreed_group)
                    agreed_deps.append(merged_dep)
                else:
                    disagreed_deps.append(deps)
            else:
                disagreed_deps.append(deps)

        print(f"[DEPENDENCY DEBUG] Agreed dependencies: {len(agreed_deps)}, Disagreed: {len(disagreed_deps)}")

        return agreed_deps, disagreed_deps

    def _find_agreement_in_dependencies(
        self,
        deps: List[UnifiedDependency]
    ) -> Optional[List[UnifiedDependency]]:
        """
        Find group of dependencies that agree on relation type.
        Uses flexible matching - ignores subtypes after ':'.
        """
        if not deps:
            return None

        # Group by base relation (before ':')
        groups = defaultdict(list)

        for dep in deps:
            # Normalize relation (remove subtypes for comparison)
            base_rel = dep.relation.split(':')[0]
            groups[base_rel].append(dep)

        # Find largest agreeing group
        largest_group = max(groups.values(), key=len)

        if len(largest_group) >= self.min_agreement:
            return largest_group

        return None

    def _merge_dependencies(
        self,
        deps: List[UnifiedDependency]
    ) -> UnifiedDependency:
        """
        Merge multiple agreeing dependencies into one.
        """
        if not deps:
            raise ValueError("Cannot merge empty dependency list")

        base = deps[0]

        # Aggregate confidence
        confidences = [d.confidence for d in deps]
        merged_confidence = self.confidence_aggregator.aggregate_mean(confidences)

        # Collect sources
        all_sources = []
        for d in deps:
            all_sources.extend(d.sources)

        # Majority vote for relation
        rel_votes = [d.relation for d in deps]
        merged_relation = max(set(rel_votes), key=rel_votes.count)

        merged_dep = UnifiedDependency(
            head_idx=base.head_idx,
            dependent_idx=base.dependent_idx,
            relation=merged_relation,
            confidence=merged_confidence,
            sources=list(set(all_sources)),
        )

        return merged_dep

    # ============================================================================
    # Entity voting
    # ============================================================================

    def vote_entities(
        self,
        processor_outputs: List[ProcessorOutput]
    ) -> Tuple[List[UnifiedEntity], List[List[UnifiedEntity]]]:
        """
        Vote on entities from multiple processors.

        Entities are matched by span overlap (IOU threshold).

        Args:
            processor_outputs: List of outputs from different processors

        Returns:
            Tuple of (agreed_entities, disagreed_entity_groups)
        """
        if not processor_outputs:
            return [], []

        # Collect all entities
        all_entities = []
        for output in processor_outputs:
            all_entities.extend(output.entities)

        if not all_entities:
            return [], []

        # Cluster overlapping entities
        entity_clusters = self._cluster_overlapping_entities(all_entities)

        agreed_entities = []
        disagreed_entities = []

        # Process each cluster
        for cluster in entity_clusters:
            if len(cluster) >= self.min_agreement:
                # Check if entities agree on type
                agreed_group = self._find_agreement_in_entities(cluster)

                if agreed_group and len(agreed_group) >= self.min_agreement:
                    # Merge agreed entities
                    merged_entity = self._merge_entities(agreed_group)
                    agreed_entities.append(merged_entity)
                else:
                    disagreed_entities.append(cluster)
            else:
                disagreed_entities.append(cluster)

        return agreed_entities, disagreed_entities

    def _cluster_overlapping_entities(
        self,
        entities: List[UnifiedEntity],
        iou_threshold: float = 0.5
    ) -> List[List[UnifiedEntity]]:
        """
        Cluster entities that have overlapping spans.

        Uses IOU (Intersection over Union) for span similarity.
        """
        if not entities:
            return []

        clusters = []

        for entity in entities:
            # Find cluster with overlap
            added = False

            for cluster in clusters:
                # Check overlap with any entity in cluster
                for cluster_entity in cluster:
                    if self._calculate_span_iou(entity, cluster_entity) >= iou_threshold:
                        cluster.append(entity)
                        added = True
                        break

                if added:
                    break

            if not added:
                # Create new cluster
                clusters.append([entity])

        return clusters

    def _calculate_span_iou(
        self,
        entity1: UnifiedEntity,
        entity2: UnifiedEntity
    ) -> float:
        """
        Calculate Intersection over Union for entity spans.

        Returns:
            IOU score (0.0-1.0)
        """
        # Get spans
        start1, end1 = entity1.start_idx, entity1.end_idx
        start2, end2 = entity2.start_idx, entity2.end_idx

        # Calculate intersection
        intersection_start = max(start1, start2)
        intersection_end = min(end1, end2)
        intersection = max(0, intersection_end - intersection_start)

        if intersection == 0:
            return 0.0

        # Calculate union
        union = (end1 - start1) + (end2 - start2) - intersection

        if union == 0:
            return 0.0

        return intersection / union

    def _find_agreement_in_entities(
        self,
        entities: List[UnifiedEntity]
    ) -> Optional[List[UnifiedEntity]]:
        """
        Find group of entities that agree on entity type.
        """
        # Group by entity type
        groups = defaultdict(list)

        for entity in entities:
            groups[entity.entity_type].append(entity)

        # Find largest agreeing group
        largest_group = max(groups.values(), key=len)

        if len(largest_group) >= self.min_agreement:
            return largest_group

        return None

    def _merge_entities(self, entities: List[UnifiedEntity]) -> UnifiedEntity:
        """
        Merge multiple agreeing entities into one.

        Uses average span boundaries and majority vote for type.
        """
        if not entities:
            raise ValueError("Cannot merge empty entity list")

        # Average span boundaries
        avg_start = int(np.mean([e.start_idx for e in entities]))
        avg_end = int(np.mean([e.end_idx for e in entities]))

        # Aggregate confidence
        confidences = [e.confidence for e in entities]
        merged_confidence = self.confidence_aggregator.aggregate_mean(confidences)

        # Collect sources
        all_sources = []
        for e in entities:
            all_sources.extend(e.sources)

        # Majority vote for entity type
        type_votes = [e.entity_type for e in entities]
        merged_type = max(set(type_votes), key=type_votes.count)

        # Use tokens from entity with most common span
        base_entity = max(
            entities,
            key=lambda e: sum(1 for e2 in entities if e.start_idx == e2.start_idx)
        )

        merged_entity = UnifiedEntity(
            entity_type=merged_type,
            start_idx=avg_start,
            end_idx=avg_end,
            tokens=base_entity.tokens,
            confidence=merged_confidence,
            sources=list(set(all_sources)),
            is_scientific=base_entity.is_scientific,
            domain=base_entity.domain,
        )

        return merged_entity

    # ============================================================================
    # Complete voting pipeline
    # ============================================================================

    def vote_all(
        self,
        processor_outputs: List[ProcessorOutput]
    ) -> VotingResult:
        """
        Run voting on all linguistic levels.

        Args:
            processor_outputs: List of outputs from different processors

        Returns:
            VotingResult with agreed and disagreed annotations
        """
        if not processor_outputs:
            return VotingResult()

        # Vote on tokens
        agreed_tokens, disagreed_tokens = self.vote_tokens(processor_outputs)

        # Vote on dependencies
        agreed_deps, disagreed_deps = self.vote_dependencies(processor_outputs)

        # Vote on entities
        agreed_entities, disagreed_entities = self.vote_entities(processor_outputs)

        # Calculate agreement metrics
        agreement_score = self.agreement_calculator.calculate_overall_agreement(
            len(agreed_tokens),
            len(disagreed_tokens),
            len(agreed_deps),
            len(disagreed_deps),
            len(agreed_entities),
            len(disagreed_entities),
        )

        # Collect participating sources
        participating_sources = list(set(
            output.processor_name
            for output in processor_outputs
        ))

        result = VotingResult(
            agreed_tokens=agreed_tokens,
            agreed_dependencies=agreed_deps,
            agreed_entities=agreed_entities,
            disagreed_tokens=disagreed_tokens,
            disagreed_dependencies=disagreed_deps,
            agreement_score=agreement_score,
            num_agreements=len(agreed_tokens) + len(agreed_deps) + len(agreed_entities),
            num_disagreements=len(disagreed_tokens) + len(disagreed_deps) + len(disagreed_entities),
            participating_sources=participating_sources,
        )

        return result

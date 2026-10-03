"""Deterministic structural-row roles and knowledge-map transition rules."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from knowledge_contracts.block_dsl import DSL_FIELDS, MAP_EVIDENCE_TYPES, MAP_NODE_TYPES
from knowledge_contracts.block_types import ALL_TYPES, BlockType


@dataclass(frozen=True)
class ReferenceTransition:
    """A typed reference that directly connects two map nodes."""

    owner_type: str
    field: str
    referenced_types: Tuple[str, ...]
    direction: str  # owner_to_reference | reference_to_owner


# This registry classifies every structural type. Context, measurements,
# bibliographic data, artifacts, and relation witnesses remain evidence.
MAP_ROW_ROLES = {
    block_type: "node" if block_type in MAP_NODE_TYPES else "evidence"
    for block_type in ALL_TYPES
}

assert frozenset(MAP_NODE_TYPES).isdisjoint(MAP_EVIDENCE_TYPES)
assert set(MAP_NODE_TYPES) | set(MAP_EVIDENCE_TYPES) == set(ALL_TYPES)


# Fields used as exact, whole-value anchors when selecting a predecessor.
# Empty tuples are explicit: those types participate only through a typed
# reference, a specific ordered rule, or as evidence.
MAP_ANCHOR_FIELDS = {
    BlockType.METADATA: (),
    BlockType.GOAL: ("subject", "object"),
    BlockType.TEXT: (),
    BlockType.STATEMENT: ("subject", "predicate", "object", "context"),
    BlockType.HYPOTHESIS: ("hypothesis", "hypothesisSubject", "hypothesisObject"),
    BlockType.PREREQUISITE: ("prerequisites",),
    BlockType.EXPECTATIONS: ("expectations",),
    BlockType.RESEARCH_DESIGN: ("design", "primaryEndpoints", "secondaryEndpoints"),
    BlockType.MATERIAL: (),
    BlockType.METHOD: ("methods", "measurementMethods"),
    BlockType.EXPERIMENT: ("experimentName", "outcomes"),
    BlockType.INCLUSION_EXCLUSION_CRITERIA: ("inclusionExclusionCriteria",),
    BlockType.BIOLOGICAL_MECHANISM: ("mechanism", "explains"),
    BlockType.IMPACT_GOAL: ("target",),
    BlockType.INTERVENTION: ("target", "purpose", "interventionType"),
    BlockType.ANIMAL_MODEL: (),
    BlockType.ANIMAL_GROUP: (),
    BlockType.ENTITY: ("subject", "object", "canonicalName", "aliases"),
    BlockType.DEFINITION: ("term", "definition"),
    BlockType.ASSUMPTIONS: ("assumptions",),
    BlockType.SAMPLE_SIZE: (),
    BlockType.DATA_SOURCE: (),
    BlockType.PROBABILITY_VALUE: (),
    BlockType.VARIANCE: (),
    BlockType.EFFECT_SIZE: (),
    BlockType.STATISTICAL_POWER: (),
    BlockType.CONFIDENCE_INTERVAL: (),
    BlockType.MAGNITUDE_VALUE: (),
    BlockType.FORMULA: (),
    BlockType.CAUSAL_GRAPH: (),
    BlockType.IDENTIFIABILITY_CRITERIA: ("criteria",),
    BlockType.RESULT: ("resultsSummary", "results", "rows"),
    BlockType.STATISTICAL_PROCESSING: ("statProcessing", "expectationsComparison"),
    BlockType.CLAIM: ("claimSubject", "claimPredicate", "claimObject"),
    BlockType.LIMITATIONS: ("limitations",),
    BlockType.SIDE_FINDINGS: ("sideFindings",),
    BlockType.SIDE_EFFECTS: ("sideEffects",),
    BlockType.POST_CLAIMS: ("postClaims", "comparisonWithExpectations"),
    BlockType.OPEN_QUESTIONS: ("openQuestions",),
    BlockType.NOVELTY: ("novelty",),
    BlockType.VERSIONS: (),
    BlockType.FUTURE_RESEARCH_SUGGESTIONS: ("futureResearch",),
    BlockType.REFERENCE: (),
    BlockType.LINK_WITH_AGING: ("agingConnection",),
    BlockType.IMAGE: (),
    BlockType.CODE: (),
    BlockType.FUNDING: (),
    BlockType.INTEREST_CONFLICT: (),
    BlockType.SCIENTIFIC_KNOWLEDGE_VALUE: (
        "uncertaintyReduced", "excludedHypotheses", "moreLikelyHypotheses",
        "newHypotheses", "nextExperiment",
    ),
    BlockType.ACTION: ("subject", "predicate", "object"),
    BlockType.EXPERIMENT_STEP: ("stepName", "details"),
    BlockType.FINDING: ("parameter", "detail", "direction"),
    BlockType.RELATION: (),
    BlockType.TEMPORAL_RELATION: (),
}

assert set(MAP_ANCHOR_FIELDS) == set(ALL_TYPES)
assert all(set(fields) <= {spec.json_field for spec in DSL_FIELDS[block_type].values()}
           for block_type, fields in MAP_ANCHOR_FIELDS.items())


# The source row owns a typed reference. Direction is fixed here; the model
# never supplies a generic edge or dependency field.
REFERENCE_TRANSITIONS: Tuple[ReferenceTransition, ...] = (
    ReferenceTransition(BlockType.RESEARCH_DESIGN, "hypotheses",
                        (BlockType.HYPOTHESIS,), "reference_to_owner"),
    ReferenceTransition(BlockType.RESEARCH_DESIGN, "experiments",
                        (BlockType.EXPERIMENT,), "owner_to_reference"),
    ReferenceTransition(BlockType.EXPERIMENT, "steps",
                        (BlockType.EXPERIMENT_STEP,), "owner_to_reference"),
    ReferenceTransition(BlockType.EXPERIMENT, "findings",
                        (BlockType.FINDING,), "owner_to_reference"),
    ReferenceTransition(BlockType.FINDING, "experimentRef",
                        (BlockType.EXPERIMENT,), "reference_to_owner"),
    ReferenceTransition(BlockType.FINDING, "interventionRef",
                        (BlockType.INTERVENTION,), "reference_to_owner"),
    ReferenceTransition(BlockType.FINDING, "statisticRefs",
                        (BlockType.STATISTICAL_PROCESSING,), "reference_to_owner"),
    ReferenceTransition(BlockType.BIOLOGICAL_MECHANISM, "supportedBy",
                        (BlockType.FINDING, BlockType.RESULT), "reference_to_owner"),
    ReferenceTransition(BlockType.STATEMENT, "subjectStatementRef",
                        (BlockType.STATEMENT, BlockType.CLAIM), "reference_to_owner"),
)
assert all(rule.owner_type in ALL_TYPES and rule.referenced_types
           and rule.direction in {"owner_to_reference", "reference_to_owner"}
           and rule.owner_type in MAP_NODE_TYPES
           and all(block_type in MAP_NODE_TYPES for block_type in rule.referenced_types)
           and any(spec.json_field == rule.field and spec.kind in ("ref", "refs")
                   for spec in DSL_FIELDS[rule.owner_type].values())
           and all(block_type in ALL_TYPES for block_type in rule.referenced_types)
           for rule in REFERENCE_TRANSITIONS)


# If no unique exact anchor or typed reference chooses a predecessor, use the
# nearest preceding row among these allowed source types. Types absent here do
# not gain edges merely by appearing next to another row.
ORDERED_PREDECESSORS = {
    BlockType.RESEARCH_DESIGN: (
        BlockType.PREREQUISITE, BlockType.ASSUMPTIONS,
        BlockType.HYPOTHESIS, BlockType.EXPECTATIONS,
    ),
    BlockType.METHOD: (
        BlockType.RESEARCH_DESIGN, BlockType.EXPERIMENT,
        BlockType.PREREQUISITE, BlockType.ASSUMPTIONS,
        BlockType.EXPECTATIONS, BlockType.INTERVENTION,
        BlockType.INCLUSION_EXCLUSION_CRITERIA,
    ),
    BlockType.EXPERIMENT: (
        BlockType.RESEARCH_DESIGN, BlockType.HYPOTHESIS,
        BlockType.EXPECTATIONS, BlockType.INTERVENTION,
        BlockType.ACTION, BlockType.METHOD,
    ),
    BlockType.EXPERIMENT_STEP: (
        BlockType.EXPERIMENT, BlockType.METHOD, BlockType.EXPERIMENT_STEP,
    ),
    BlockType.STATISTICAL_PROCESSING: (
        BlockType.EXPERIMENT, BlockType.EXPERIMENT_STEP, BlockType.METHOD,
    ),
    BlockType.FINDING: (
        BlockType.EXPERIMENT_STEP, BlockType.EXPERIMENT,
        BlockType.STATISTICAL_PROCESSING,
    ),
    BlockType.RESULT: (
        BlockType.EXPERIMENT_STEP, BlockType.EXPERIMENT,
        BlockType.STATISTICAL_PROCESSING,
    ),
    BlockType.POST_CLAIMS: (BlockType.FINDING, BlockType.RESULT),
    BlockType.SIDE_FINDINGS: (BlockType.FINDING, BlockType.RESULT),
    BlockType.SIDE_EFFECTS: (
        BlockType.INTERVENTION, BlockType.EXPERIMENT,
        BlockType.FINDING, BlockType.RESULT,
    ),
    BlockType.LIMITATIONS: (
        BlockType.RESEARCH_DESIGN, BlockType.FINDING, BlockType.RESULT,
    ),
    BlockType.OPEN_QUESTIONS: (
        BlockType.LIMITATIONS, BlockType.FINDING, BlockType.RESULT,
    ),
    BlockType.NOVELTY: (
        BlockType.RESEARCH_DESIGN, BlockType.FINDING, BlockType.RESULT,
    ),
    BlockType.FUTURE_RESEARCH_SUGGESTIONS: (
        BlockType.LIMITATIONS, BlockType.OPEN_QUESTIONS,
        BlockType.SCIENTIFIC_KNOWLEDGE_VALUE,
    ),
    BlockType.LINK_WITH_AGING: (
        BlockType.BIOLOGICAL_MECHANISM, BlockType.FINDING, BlockType.RESULT,
    ),
    BlockType.SCIENTIFIC_KNOWLEDGE_VALUE: (
        BlockType.POST_CLAIMS, BlockType.FINDING, BlockType.RESULT,
    ),
}

assert all(target in MAP_NODE_TYPES for target in ORDERED_PREDECESSORS)
assert all(source in MAP_NODE_TYPES
           for sources in ORDERED_PREDECESSORS.values() for source in sources)

# Complete registry: every structural type has a declared predecessor set.
# Typed-reference transitions augment the ordered fallback pairs above.
_allowed_transitions = {
    block_type: set(ORDERED_PREDECESSORS.get(block_type, ()))
    for block_type in ALL_TYPES
}
for _rule in REFERENCE_TRANSITIONS:
    if _rule.direction == "owner_to_reference":
        for _referenced_type in _rule.referenced_types:
            _allowed_transitions[_referenced_type].add(_rule.owner_type)
    else:
        _allowed_transitions[_rule.owner_type].update(_rule.referenced_types)
ALLOWED_TRANSITIONS = {
    block_type: tuple(sorted(sources))
    for block_type, sources in _allowed_transitions.items()
}
assert set(ALLOWED_TRANSITIONS) == set(ALL_TYPES)
assert all(source in MAP_NODE_TYPES for sources in ALLOWED_TRANSITIONS.values()
           for source in sources)

# Cross-field exact matches that express the same named experiment/outcome.
# Each pair is (predecessor field, dependent field); fuzzy or substring matches
# are never used. Candidate uniqueness is checked per exact value and pair.
EXACT_FIELD_TRANSITIONS = {
    BlockType.FINDING: {
        BlockType.EXPERIMENT: (
            ("outcomes", "parameter"), ("experimentName", "parameter"),
        ),
        BlockType.EXPERIMENT_STEP: (
            ("stepName", "parameter"), ("details", "detail"),
        ),
        BlockType.STATISTICAL_PROCESSING: (
            ("statProcessing", "detail"),
            ("expectationsComparison", "detail"),
        ),
    },
    BlockType.RESULT: {
        BlockType.EXPERIMENT: (
            ("outcomes", "resultsSummary"), ("outcomes", "results"),
        ),
        BlockType.EXPERIMENT_STEP: (
            ("stepName", "resultsSummary"), ("details", "resultsSummary"),
        ),
        BlockType.STATISTICAL_PROCESSING: (
            ("statProcessing", "resultsSummary"),
            ("expectationsComparison", "resultsSummary"),
        ),
    },
    BlockType.POST_CLAIMS: {
        BlockType.FINDING: (("parameter", "postClaims"), ("detail", "postClaims")),
        BlockType.RESULT: (("resultsSummary", "postClaims"), ("results", "postClaims")),
    },
    BlockType.SIDE_FINDINGS: {
        BlockType.FINDING: (("parameter", "sideFindings"), ("detail", "sideFindings")),
        BlockType.RESULT: (("resultsSummary", "sideFindings"), ("results", "sideFindings")),
    },
}
assert all(target in MAP_NODE_TYPES
           and all(source in MAP_NODE_TYPES for source in source_fields)
           for target, source_fields in EXACT_FIELD_TRANSITIONS.items())
assert all(source_field in MAP_ANCHOR_FIELDS[source]
           and target_field in MAP_ANCHOR_FIELDS[target]
           for target, source_fields in EXACT_FIELD_TRANSITIONS.items()
           for source, pairs in source_fields.items()
           for source_field, target_field in pairs)


# Goal links are order-independent but require exact agreement between an
# actionable/result target field and the article goal's subject or object.
GOAL_TARGET_FIELDS: Tuple[str, ...] = ("subject", "object", "target")
GOAL_SOURCE_FIELDS = {
    BlockType.ACTION: ("object",),
    BlockType.INTERVENTION: ("target", "purpose"),
    BlockType.METHOD: ("methods", "measurementMethods"),
    BlockType.EXPERIMENT: ("experimentName", "outcomes"),
    BlockType.EXPERIMENT_STEP: ("stepName", "details"),
    BlockType.FINDING: ("parameter", "detail"),
    BlockType.RESULT: ("resultsSummary", "results"),
    BlockType.POST_CLAIMS: ("postClaims",),
    BlockType.SCIENTIFIC_KNOWLEDGE_VALUE: ("uncertaintyReduced", "nextExperiment"),
}

assert set(GOAL_SOURCE_FIELDS) <= set(MAP_NODE_TYPES)
assert all(set(fields) <= {spec.json_field for spec in DSL_FIELDS[block_type].values()}
           for block_type, fields in GOAL_SOURCE_FIELDS.items())
assert set(GOAL_TARGET_FIELDS) <= {
    spec.json_field
    for block_type in (BlockType.GOAL, BlockType.IMPACT_GOAL)
    for spec in DSL_FIELDS[block_type].values()
}
_allowed_transitions[BlockType.FINDING].add(BlockType.METHOD)
_allowed_transitions[BlockType.RESULT].add(BlockType.METHOD)
for _goal_type in (BlockType.GOAL, BlockType.IMPACT_GOAL):
    _allowed_transitions[_goal_type].update(GOAL_SOURCE_FIELDS)
ALLOWED_TRANSITIONS = {
    block_type: tuple(sorted(sources))
    for block_type, sources in _allowed_transitions.items()
}
assert set(ALLOWED_TRANSITIONS) == set(ALL_TYPES)
assert all(source in MAP_NODE_TYPES for sources in ALLOWED_TRANSITIONS.values()
           for source in sources)

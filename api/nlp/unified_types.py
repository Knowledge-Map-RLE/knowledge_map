"""
Unified data types for multi-level linguistic analysis.

This module defines universal data structures that unify outputs from different NLP tools
(spaCy, NLTK, UDPipe, etc.) into a common format based on Universal Dependencies.

All linguistic entities use confidence scores and track their sources (which models agree).
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Any
from enum import Enum


class LinguisticLevel(Enum):
    """Linguistic analysis levels."""
    TOKENIZATION = 1
    MORPHOLOGY = 2
    SYNTAX = 3
    SEMANTIC_ROLES = 4
    LEXICAL_SEMANTICS = 5
    DISCOURSE = 6


@dataclass
class UnifiedToken:
    """
    Universal token representation across all NLP processors.

    Follows Universal Dependencies standards for POS tags and morphological features.
    """
    # Position and text
    idx: int                              # Token index in sentence
    text: str                             # Original text
    start_char: int                       # Character offset in document
    end_char: int                         # Character offset in document

    # Morphology
    lemma: str                            # Lemmatized form
    pos: str                              # Universal POS tag (NOUN, VERB, ADJ, etc.)
    pos_fine: Optional[str] = None        # Fine-grained POS tag
    morph: Dict[str, str] = field(default_factory=dict)  # Morphological features

    # Confidence and sources
    confidence: float = 1.0               # Aggregated confidence (0.0-1.0)
    sources: List[str] = field(default_factory=list)  # ['spacy', 'udpipe', ...]

    # Additional features
    is_stop: bool = False
    is_punct: bool = False
    is_space: bool = False

    # Scientific domain
    is_scientific_term: bool = False
    scientific_category: Optional[str] = None

    def __hash__(self):
        return hash((self.idx, self.text, self.start_char))


@dataclass
class UnifiedDependency:
    """
    Universal dependency relation between tokens.

    Follows Universal Dependencies relation taxonomy.
    """
    head_idx: int                         # Head token index
    dependent_idx: int                    # Dependent token index
    relation: str                         # UD relation type (nsubj, obj, amod, etc.)

    # Confidence and sources
    confidence: float = 1.0
    sources: List[str] = field(default_factory=list)

    # Additional info
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class UnifiedPhrase:
    """
    Phrase/constituent structure.

    Represents multi-word expressions, noun phrases, verb phrases, etc.
    """
    phrase_type: str                      # NP, VP, PP, ADJP, ADVP, etc.
    start_idx: int                        # First token index
    end_idx: int                          # Last token index (exclusive)
    tokens: List[UnifiedToken]            # Tokens in this phrase
    head_idx: int                         # Index of head token

    # Confidence and sources
    confidence: float = 1.0
    sources: List[str] = field(default_factory=list)

    # Hierarchical structure
    parent_phrase: Optional['UnifiedPhrase'] = None
    children_phrases: List['UnifiedPhrase'] = field(default_factory=list)

    def text(self) -> str:
        """Get phrase text."""
        return " ".join(t.text for t in self.tokens)


@dataclass
class UnifiedSemanticRole:
    """
    Semantic role (argument) of a predicate.

    Follows PropBank/FrameNet conventions.
    """
    predicate_idx: int                    # Predicate token index
    predicate_lemma: str                  # Predicate lemma
    role: str                             # ARG0, ARG1, ARG2, ARGM-LOC, ARGM-TMP, etc.

    # Argument span
    arg_start_idx: int
    arg_end_idx: int                      # Exclusive

    # Optional fields
    role_description: Optional[str] = None  # Human-readable description
    arg_tokens: List[UnifiedToken] = field(default_factory=list)

    # Confidence and sources
    confidence: float = 1.0
    sources: List[str] = field(default_factory=list)

    # Frame information (if using FrameNet)
    frame: Optional[str] = None
    frame_element: Optional[str] = None

    def arg_text(self) -> str:
        """Get argument text."""
        return " ".join(t.text for t in self.arg_tokens)


@dataclass
class UnifiedEntity:
    """
    Named entity or scientific entity.
    """
    entity_type: str                      # PERSON, ORG, GPE, GENE, PROTEIN, DISEASE, etc.
    start_idx: int
    end_idx: int                          # Exclusive
    tokens: List[UnifiedToken]

    # Confidence and sources
    confidence: float = 1.0
    sources: List[str] = field(default_factory=list)

    # Entity linking
    entity_id: Optional[str] = None       # KB ID (e.g., UniProt ID, MeSH ID)
    canonical_name: Optional[str] = None

    # Scientific domain
    is_scientific: bool = False
    domain: Optional[str] = None          # biology, chemistry, physics, etc.

    def text(self) -> str:
        """Get entity text."""
        return " ".join(t.text for t in self.tokens)


@dataclass
class UnifiedRelation:
    """
    Semantic relation between entities or concepts.

    Examples: CAUSE, EFFECT, PART-OF, IS-A, TREATS, INHIBITS
    """
    source_entity: UnifiedEntity
    target_entity: UnifiedEntity
    relation_type: str                    # Relation label

    # Confidence and sources
    confidence: float = 1.0
    sources: List[str] = field(default_factory=list)

    # Relation evidence
    evidence_text: Optional[str] = None   # Text span that expresses this relation
    evidence_start_idx: Optional[int] = None
    evidence_end_idx: Optional[int] = None

    # Directionality
    is_directed: bool = True

    # Additional info
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class UnifiedCoreference:
    """
    Coreference cluster - entities referring to the same real-world entity.
    """
    cluster_id: int
    mentions: List[UnifiedEntity]         # All mentions in the cluster
    representative_mention: Optional[UnifiedEntity] = None  # Canonical mention

    # Confidence and sources
    confidence: float = 1.0
    sources: List[str] = field(default_factory=list)


@dataclass
class UnifiedSentence:
    """
    Complete sentence analysis with all linguistic levels.
    """
    # Basic info
    idx: int                              # Sentence index in document
    text: str
    start_char: int
    end_char: int

    # Level 1: Tokenization
    tokens: List[UnifiedToken] = field(default_factory=list)

    # Level 2: Morphology (already in tokens)

    # Level 3: Syntax
    dependencies: List[UnifiedDependency] = field(default_factory=list)
    phrases: List[UnifiedPhrase] = field(default_factory=list)
    root_idx: Optional[int] = None        # Index of root token

    # Level 4: Semantic roles
    semantic_roles: List[UnifiedSemanticRole] = field(default_factory=list)
    predicates: List[int] = field(default_factory=list)  # Indices of predicate tokens

    # Level 5: Lexical semantics
    entities: List[UnifiedEntity] = field(default_factory=list)

    # Level 6: Discourse
    discourse_relations: List['UnifiedDiscourseRelation'] = field(default_factory=list)

    # Overall confidence
    confidence: float = 1.0


@dataclass
class UnifiedDiscourseRelation:
    """
    Discourse relation between sentences or clauses.

    Examples: CAUSE-EFFECT, CONTRAST, ELABORATION, TEMPORAL
    """
    relation_type: str                    # RST relation type
    source_sentence_idx: int
    target_sentence_idx: int

    # Nuclearity (for RST)
    source_is_nucleus: bool = True
    target_is_nucleus: bool = False

    # Confidence and sources
    confidence: float = 1.0
    sources: List[str] = field(default_factory=list)

    # Evidence
    discourse_marker: Optional[str] = None  # "however", "because", "therefore", etc.


@dataclass
class UnifiedDocument:
    """
    Complete document analysis with all sentences and document-level features.
    """
    # Document info
    doc_id: str
    text: str

    # Sentences
    sentences: List[UnifiedSentence] = field(default_factory=list)

    # Document-level entities and relations
    entities: List[UnifiedEntity] = field(default_factory=list)
    relations: List[UnifiedRelation] = field(default_factory=list)

    # Coreference
    coreference_clusters: List[UnifiedCoreference] = field(default_factory=list)

    # Document-level discourse
    discourse_structure: List[UnifiedDiscourseRelation] = field(default_factory=list)

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Processing info
    processed_levels: List[LinguisticLevel] = field(default_factory=list)
    processing_time: float = 0.0


# ============================================================================
# Helper classes for voting and agreement
# ============================================================================

@dataclass
class ProcessorOutput:
    """
    Output from a single NLP processor (before voting).
    """
    processor_name: str                   # 'spacy', 'udpipe', 'nltk', etc.
    processor_version: str

    # Raw outputs (processor-specific)
    tokens: List[UnifiedToken] = field(default_factory=list)
    dependencies: List[UnifiedDependency] = field(default_factory=list)
    entities: List[UnifiedEntity] = field(default_factory=list)
    # ... other outputs

    # Confidence
    overall_confidence: float = 1.0

    # Timing
    processing_time: float = 0.0


@dataclass
class VotingResult:
    """
    Result of voting between multiple processors.
    """
    # Agreed outputs (confidence >= threshold, min 2 sources)
    agreed_tokens: List[UnifiedToken] = field(default_factory=list)
    agreed_dependencies: List[UnifiedDependency] = field(default_factory=list)
    agreed_entities: List[UnifiedEntity] = field(default_factory=list)

    # Disagreed outputs (could not reach consensus)
    disagreed_tokens: List[List[UnifiedToken]] = field(default_factory=list)
    disagreed_dependencies: List[List[UnifiedDependency]] = field(default_factory=list)

    # Agreement metrics
    agreement_score: float = 0.0          # Overall agreement (0.0-1.0)
    num_agreements: int = 0
    num_disagreements: int = 0

    # Sources that participated
    participating_sources: List[str] = field(default_factory=list)


# ============================================================================
# Constants
# ============================================================================

# Universal Dependencies POS tags
UD_POS_TAGS = [
    'ADJ',    # adjective
    'ADP',    # adposition
    'ADV',    # adverb
    'AUX',    # auxiliary
    'CCONJ',  # coordinating conjunction
    'DET',    # determiner
    'INTJ',   # interjection
    'NOUN',   # noun
    'NUM',    # numeral
    'PART',   # particle
    'PRON',   # pronoun
    'PROPN',  # proper noun
    'PUNCT',  # punctuation
    'SCONJ',  # subordinating conjunction
    'SYM',    # symbol
    'VERB',   # verb
    'X',      # other
]

# Universal Dependencies relations
UD_RELATIONS = [
    'nsubj', 'obj', 'iobj', 'csubj', 'ccomp', 'xcomp',
    'obl', 'vocative', 'expl', 'dislocated', 'advcl', 'advmod',
    'discourse', 'aux', 'cop', 'mark', 'nmod', 'appos', 'nummod',
    'acl', 'amod', 'det', 'clf', 'case', 'conj', 'cc', 'fixed',
    'flat', 'compound', 'list', 'parataxis', 'orphan', 'goeswith',
    'reparandum', 'punct', 'root', 'dep',
]

# PropBank semantic roles
PROPBANK_ROLES = [
    'ARG0',  # Agent
    'ARG1',  # Patient/Theme
    'ARG2',  # Instrument/Benefactive/Attribute
    'ARG3',  # Starting point/Benefactive/Attribute
    'ARG4',  # Ending point
    'ARG5',  # Unused
    'ARGM-ADJ',  # Adjectival
    'ARGM-ADV',  # Adverbial
    'ARGM-CAU',  # Cause
    'ARGM-DIR',  # Direction
    'ARGM-DIS',  # Discourse
    'ARGM-EXT',  # Extent
    'ARGM-GOL',  # Goal
    'ARGM-LOC',  # Location
    'ARGM-MNR',  # Manner
    'ARGM-MOD',  # Modal
    'ARGM-NEG',  # Negation
    'ARGM-PRD',  # Predication
    'ARGM-PRP',  # Purpose
    'ARGM-TMP',  # Temporal
]

# Common scientific entity types
SCIENTIFIC_ENTITY_TYPES = [
    # Biology
    'GENE', 'PROTEIN', 'ENZYME', 'DNA', 'RNA', 'CELL', 'ORGANISM',
    'DISEASE', 'SYMPTOM', 'DRUG', 'CHEMICAL', 'TISSUE', 'ORGAN',

    # Chemistry
    'MOLECULE', 'COMPOUND', 'ELEMENT', 'REACTION', 'FORMULA',

    # Physics/Math
    'EQUATION', 'THEOREM', 'CONSTANT', 'UNIT', 'MEASUREMENT',

    # General scientific
    'METHOD', 'PROCEDURE', 'INSTRUMENT', 'SOFTWARE', 'DATASET',
    'CITATION', 'FIGURE', 'TABLE',
]

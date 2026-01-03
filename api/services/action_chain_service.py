"""
Action Chain Service

Builds chains of actions (verb ontologies) from linguistic ontologies in Neo4j.
Determines sequence relationships between actions based on:
1. Direct syntactic dependencies (xcomp, advcl, etc.)
2. Sequence markers (after, then, before, etc.)
3. Text position (sent_idx, token_idx)
4. Shared entities (common objects/subjects)
"""

from neo4j import GraphDatabase
import json
import os
import logging
from typing import List, Dict, Any, Optional, Generator, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class SequenceType(Enum):
    """Types of action sequences"""
    TEMPORAL_AFTER = "TEMPORAL_AFTER"      # Action happens after another
    TEMPORAL_BEFORE = "TEMPORAL_BEFORE"     # Action happens before another
    CAUSAL = "CAUSAL"                       # Causality relationship
    PURPOSE = "PURPOSE"                     # Purpose/goal relationship
    RESULT = "RESULT"                       # Result relationship
    COORDINATION = "COORDINATION"           # Parallel/coordinated actions
    SEQUENTIAL = "SEQUENTIAL"               # General sequential order


# Sequence markers mapping
SEQUENCE_MARKERS = {
    # Temporal markers
    'after': SequenceType.TEMPORAL_AFTER,
    'then': SequenceType.TEMPORAL_AFTER,
    'next': SequenceType.TEMPORAL_AFTER,
    'following': SequenceType.TEMPORAL_AFTER,
    'subsequently': SequenceType.TEMPORAL_AFTER,
    'before': SequenceType.TEMPORAL_BEFORE,
    'previously': SequenceType.TEMPORAL_BEFORE,
    'first': SequenceType.TEMPORAL_BEFORE,
    'finally': SequenceType.TEMPORAL_AFTER,

    # Causal markers
    'because': SequenceType.CAUSAL,
    'therefore': SequenceType.RESULT,
    'thus': SequenceType.RESULT,
    'consequently': SequenceType.RESULT,
    'hence': SequenceType.RESULT,

    # Purpose markers
    'to': SequenceType.PURPOSE,
    'in order to': SequenceType.PURPOSE,
    'so that': SequenceType.PURPOSE,
}

# Dependency relations mapping
DEPENDENCY_MAPPING = {
    'xcomp': SequenceType.PURPOSE,        # "want to go"
    'advcl': SequenceType.TEMPORAL_AFTER, # "after eating, left"
    'ccomp': SequenceType.RESULT,         # "said that..."
    'conj': SequenceType.COORDINATION,    # "and", coordinated actions
}


@dataclass
class VerbOntology:
    """Represents a verb ontology with its metadata"""
    ontology_id: str
    verb_text: str
    verb_lemma: str
    sent_idx: int
    token_idx: int
    source_token_uid: str
    confidence: float
    subject: Optional[str] = None
    object: Optional[str] = None
    arguments: Optional[List[str]] = None

    # Backward compatibility alias
    @property
    def pattern_id(self) -> str:
        """Backward compatibility: pattern_id is now ontology_id"""
        return self.ontology_id


@dataclass
class ActionSequence:
    """Represents a sequence relationship between two actions"""
    from_ontology_id: str
    to_ontology_id: str
    sequence_type: SequenceType
    confidence: float
    evidence: List[str]

    # Backward compatibility aliases
    @property
    def from_pattern_id(self) -> str:
        """Backward compatibility: from_pattern_id is now from_ontology_id"""
        return self.from_ontology_id

    @property
    def to_pattern_id(self) -> str:
        """Backward compatibility: to_pattern_id is now to_ontology_id"""
        return self.to_ontology_id


class ActionChainService:
    def __init__(self):
        neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        neo4j_user = os.getenv("NEO4J_USER", "neo4j")
        neo4j_password = os.getenv("NEO4J_PASSWORD", "password")

        self.driver = GraphDatabase.driver(
            neo4j_uri,
            auth=(neo4j_user, neo4j_password)
        )

        # Cache for all tokens (loaded once)
        self._all_tokens_cache = None

    def close(self):
        """Close the Neo4j driver connection"""
        self.driver.close()

    def extract_verb_ontologies(self) -> List[VerbOntology]:
        """
        Extract all verb ontologies with their metadata and arguments
        """
        with self.driver.session() as session:
            query = """
            // Get all verb ontologies
            MATCH (o:Ontology)-[:HAS_POS]->(pos:OntologyProperty {type: 'pos', value: 'VERB'})
            MATCH (o)-[:HAS_TEXT]->(text:OntologyProperty {type: 'text'})
            MATCH (o)-[:HAS_LEMMA]->(lemma:OntologyProperty {type: 'lemma'})
            MATCH (o)-[:HAS_CONFIDENCE]->(conf:OntologyProperty {type: 'confidence'})

            // Get subject (nsubj)
            OPTIONAL MATCH (o)<-[r_subj:SYNTACTIC_RELATION {relation_type: 'nsubj'}]-(subj:Ontology)
            OPTIONAL MATCH (subj)-[:HAS_TEXT]->(subj_text:OntologyProperty {type: 'text'})

            // Get object (obj)
            OPTIONAL MATCH (o)-[r_obj:SYNTACTIC_RELATION {relation_type: 'obj'}]->(obj:Ontology)
            OPTIONAL MATCH (obj)-[:HAS_TEXT]->(obj_text:OntologyProperty {type: 'text'})

            // Get all arguments (oblique, etc.)
            OPTIONAL MATCH (o)-[r_arg:SYNTACTIC_RELATION]->(arg:Ontology)
            WHERE r_arg.relation_type IN ['obl', 'iobj', 'xcomp', 'ccomp']
            OPTIONAL MATCH (arg)-[:HAS_TEXT]->(arg_text:OntologyProperty {type: 'text'})

            WITH o, text, lemma, conf, subj_text, obj_text, COLLECT(DISTINCT arg_text.value) as arguments

            RETURN
                o.ontology_id as ontology_id,
                text.value as verb_text,
                lemma.value as verb_lemma,
                conf.value as confidence,
                o.source_token_uid as source_token_uid,
                o.sent_idx as sent_idx,
                o.token_idx as token_idx,
                subj_text.value as subject,
                obj_text.value as object,
                arguments
            ORDER BY o.sent_idx ASC, o.token_idx ASC
            """

            result = session.run(query)
            verbs = []

            for record in result:
                verb = VerbOntology(
                    ontology_id=record['ontology_id'],
                    verb_text=record['verb_text'],
                    verb_lemma=record['verb_lemma'],
                    sent_idx=record['sent_idx'],
                    token_idx=record['token_idx'],
                    source_token_uid=record['source_token_uid'],
                    confidence=record['confidence'],
                    subject=record['subject'],
                    object=record['object'],
                    arguments=record['arguments'] if record['arguments'] else []
                )
                verbs.append(verb)

            logger.info(f"Extracted {len(verbs)} verb ontologies")
            return verbs

    # Backward compatibility alias
    def extract_verb_patterns(self) -> List[VerbOntology]:
        """Backward compatibility: extract_verb_patterns calls extract_verb_ontologies"""
        return self.extract_verb_ontologies()

    def find_direct_dependency(self, verb1: VerbOntology, verb2: VerbOntology) -> Optional[str]:
        """
        Check if there's a direct syntactic dependency between two verbs
        """
        with self.driver.session() as session:
            query = """
            MATCH (o1:Ontology {ontology_id: $id1})
            MATCH (o2:Ontology {ontology_id: $id2})
            MATCH (o1)-[r:SYNTACTIC_RELATION]-(o2)
            WHERE r.relation_type IN ['xcomp', 'advcl', 'ccomp', 'conj']
            RETURN r.relation_type as rel_type, startNode(r) = o1 as is_outgoing
            """

            result = session.run(query, id1=verb1.ontology_id, id2=verb2.ontology_id)
            record = result.single()

            if record:
                return record['rel_type']

            return None

    def _load_all_tokens(self):
        """Load all tokens once and cache them"""
        if self._all_tokens_cache is not None:
            return self._all_tokens_cache

        with self.driver.session() as session:
            query = """
            MATCH (o:Ontology)-[:HAS_TEXT]->(text:OntologyProperty {type: 'text'})
            WHERE o.concept_type = 'token'
            RETURN text.value as text, o.sent_idx as sent_idx, o.token_idx as token_idx
            """

            result = session.run(query)
            tokens = []

            for record in result:
                try:
                    tokens.append({
                        'text': record['text'].lower(),
                        'sent_idx': record['sent_idx'],
                        'token_idx': record['token_idx']
                    })
                except (KeyError, TypeError):
                    continue

            self._all_tokens_cache = tokens
            return tokens

    def find_sequence_markers(self, verb1: VerbOntology, verb2: VerbOntology) -> List[Dict[str, Any]]:
        """
        Find sequence markers between two verbs
        """
        tokens = self._load_all_tokens()
        markers = []

        for token in tokens:
            text = token['text']
            sent_idx = token['sent_idx']
            token_idx = token['token_idx']

            # Check if this token is between verb1 and verb2
            is_between = False

            if verb1.sent_idx == verb2.sent_idx == sent_idx:
                # Same sentence: check token position
                if verb1.token_idx < token_idx < verb2.token_idx:
                    is_between = True
            elif verb1.sent_idx < sent_idx < verb2.sent_idx:
                # Between sentences
                is_between = True

            if is_between and text in SEQUENCE_MARKERS:
                markers.append({
                    'text': text,
                    'type': SEQUENCE_MARKERS[text]
                })

        return markers

    def find_shared_entities(self, verb1: VerbOntology, verb2: VerbOntology) -> List[str]:
        """
        Find shared entities (objects, subjects) between two verb ontologies
        """
        entities1 = set([verb1.subject, verb1.object] + (verb1.arguments or []))
        entities2 = set([verb2.subject, verb2.object] + (verb2.arguments or []))

        entities1.discard(None)
        entities2.discard(None)

        shared = entities1 & entities2
        return list(shared)

    def determine_action_sequence(
        self,
        verb1: VerbOntology,
        verb2: VerbOntology
    ) -> Optional[ActionSequence]:
        """
        Determine if two verb patterns form an action sequence
        Returns ActionSequence with confidence score and evidence

        STRICT CRITERIA to avoid over-connection:
        - Requires STRONG linguistic evidence (direct dependency OR marker)
        - OR very close position (same/adjacent sentence) WITH shared entities
        - High confidence threshold (0.7) to ensure quality
        """
        confidence = 0.0
        evidence = []
        sequence_type = SequenceType.SEQUENTIAL
        has_strong_evidence = False

        # Skip if same ontology
        if verb1.ontology_id == verb2.ontology_id:
            return None

        # Skip if verb2 comes before verb1 in text
        if verb2.sent_idx < verb1.sent_idx:
            return None
        if verb2.sent_idx == verb1.sent_idx and verb2.token_idx <= verb1.token_idx:
            return None

        # 1. Check direct linguistic dependency (STRONG evidence: 0.7)
        direct_dep = self.find_direct_dependency(verb1, verb2)
        if direct_dep:
            sequence_type = DEPENDENCY_MAPPING.get(direct_dep, SequenceType.SEQUENTIAL)
            confidence += 0.7
            evidence.append(f"direct_dependency:{direct_dep}")
            has_strong_evidence = True

        # 2. Check sequence markers (STRONG evidence: 0.6)
        markers = self.find_sequence_markers(verb1, verb2)
        if markers:
            sequence_type = markers[0]['type']
            confidence += 0.6
            evidence.append(f"marker:{markers[0]['text']}")
            has_strong_evidence = True

        # 3. Check shared entities (REQUIRED for weak connections)
        shared_entities = self.find_shared_entities(verb1, verb2)
        if shared_entities:
            confidence += 0.3
            evidence.append(f"shared_entities:{','.join(shared_entities)}")

        # 4. Position bonus (ONLY for very close verbs)
        sent_diff = verb2.sent_idx - verb1.sent_idx
        if sent_diff == 0:
            # Same sentence - small bonus
            confidence += 0.15
            evidence.append("same_sentence")
        elif sent_diff == 1 and shared_entities:
            # Adjacent sentences WITH shared entities
            confidence += 0.2
            evidence.append("adjacent_with_shared_entity")

        # STRICT decision logic:
        # 1. Must have strong evidence (dependency or marker)
        #    OR be in same/adjacent sentence with shared entities
        # 2. Must meet confidence threshold of 0.7

        if not has_strong_evidence:
            # Without strong evidence, need same/adjacent sentences AND shared entities
            if sent_diff > 1 or not shared_entities:
                return None

        # High confidence threshold to prevent over-connection
        if confidence >= 0.7:
            return ActionSequence(
                from_ontology_id=verb1.ontology_id,
                to_ontology_id=verb2.ontology_id,
                sequence_type=sequence_type,
                confidence=min(confidence, 1.0),
                evidence=evidence
            )

        return None

    def build_action_chains(self) -> Generator[Dict[str, Any], None, None]:
        """
        Build action chains from verb ontologies with progress reporting
        """
        # Extract all verb ontologies
        yield {
            "stage": "extracting_verbs",
            "message": "Extracting verb ontologies..."
        }

        verbs = self.extract_verb_ontologies()
        total_pairs = len(verbs) * (len(verbs) - 1) // 2

        yield {
            "stage": "extracted_verbs",
            "total_verbs": len(verbs),
            "total_pairs": total_pairs,
            "message": f"Found {len(verbs)} verb ontologies, analyzing {total_pairs} pairs..."
        }

        # Analyze pairs and build sequences
        sequences = []
        processed_pairs = 0

        for i, verb1 in enumerate(verbs):
            for verb2 in verbs[i+1:]:
                sequence = self.determine_action_sequence(verb1, verb2)
                if sequence:
                    sequences.append(sequence)

                processed_pairs += 1

                if processed_pairs % 100 == 0:
                    yield {
                        "stage": "analyzing_pairs",
                        "processed": processed_pairs,
                        "total": total_pairs,
                        "percentage": int((processed_pairs / total_pairs) * 100),
                        "sequences_found": len(sequences),
                        "message": f"Analyzed {processed_pairs}/{total_pairs} pairs, found {len(sequences)} sequences"
                    }

        yield {
            "stage": "creating_relationships",
            "sequences_found": len(sequences),
            "message": f"Creating {len(sequences)} action sequence relationships in Neo4j..."
        }

        # Create relationships in Neo4j
        created_count = self._create_action_sequences(sequences)

        # Link shared entities
        yield {
            "stage": "linking_entities",
            "message": "Linking shared entities between patterns..."
        }

        entity_links = self._link_shared_entities(sequences)

        # Get statistics
        stats = self._get_statistics()

        yield {
            "stage": "complete",
            "message": "Action chains built successfully",
            "statistics": {
                "total_verbs": len(verbs),
                "action_sequences": created_count,
                "entity_links": entity_links,
                **stats
            }
        }

    def _would_create_cycle(self, from_id: str, to_id: str) -> bool:
        """
        Check if adding edge from_id -> to_id would create a cycle (violate DAG)
        Returns True if cycle would be created
        """
        with self.driver.session() as session:
            # Check if there's already a path from to_id to from_id
            # If yes, adding from_id -> to_id would create a cycle
            query = """
            MATCH (start:Ontology {ontology_id: $to_id})
            MATCH (end:Ontology {ontology_id: $from_id})
            MATCH path = (start)-[:ACTION_SEQUENCE*]->(end)
            RETURN count(path) > 0 as has_path
            """

            result = session.run(query, from_id=from_id, to_id=to_id)
            record = result.single()
            return record['has_path'] if record else False

    def _create_action_sequences(self, sequences: List[ActionSequence]) -> int:
        """
        Create ACTION_SEQUENCE relationships in Neo4j
        Ensures DAG structure by checking for cycles before adding each edge
        Uses MERGE to avoid duplicates - updates existing relationships instead
        """
        with self.driver.session() as session:
            created = 0
            updated = 0
            skipped_cycles = 0

            for seq in sequences:
                # Check if this would create a cycle
                if self._would_create_cycle(seq.from_ontology_id, seq.to_ontology_id):
                    skipped_cycles += 1
                    continue

                # Use MERGE to create or update relationship
                # This prevents duplicates by matching on nodes only
                query = """
                MATCH (o1:Ontology {ontology_id: $from_id})
                MATCH (o2:Ontology {ontology_id: $to_id})

                // Check if relationship already exists
                OPTIONAL MATCH (o1)-[existing:ACTION_SEQUENCE]->(o2)

                WITH o1, o2, existing, existing IS NULL as is_new

                MERGE (o1)-[r:ACTION_SEQUENCE]->(o2)
                ON CREATE SET
                    r.sequence_type = $sequence_type,
                    r.confidence = $confidence,
                    r.evidence = $evidence,
                    r.created_at = timestamp()
                ON MATCH SET
                    r.sequence_type = $sequence_type,
                    r.confidence = $confidence,
                    r.evidence = $evidence,
                    r.updated_at = timestamp()

                RETURN is_new
                """

                result = session.run(
                    query,
                    from_id=seq.from_ontology_id,
                    to_id=seq.to_ontology_id,
                    sequence_type=seq.sequence_type.value,
                    confidence=seq.confidence,
                    evidence=seq.evidence
                )

                record = result.single()
                if record and record['is_new']:
                    created += 1
                else:
                    updated += 1

            if skipped_cycles > 0:
                logger.info(f"Skipped {skipped_cycles} sequences to maintain DAG structure")

            if updated > 0:
                logger.info(f"Updated {updated} existing sequences")

            return created

    def _link_shared_entities(self, sequences: List[ActionSequence]) -> int:
        """
        Create SAME_ENTITY links between properties with the same text value
        """
        with self.driver.session() as session:
            query = """
            MATCH (op1:OntologyProperty {type: 'text'})
            MATCH (op2:OntologyProperty {type: 'text'})
            WHERE op1.value = op2.value
              AND id(op1) < id(op2)
              AND op1.value IS NOT NULL
              AND op1.value <> ''
            MERGE (op1)-[r:SAME_ENTITY {
                confidence: 1.0,
                created_at: timestamp()
            }]-(op2)
            RETURN count(r) as count
            """

            result = session.run(query)
            return result.single()['count']

    def _get_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about action chains
        """
        with self.driver.session() as session:
            query = """
            MATCH ()-[r:ACTION_SEQUENCE]->()
            WITH
                count(r) as total_sequences,
                collect({type: r.sequence_type, confidence: r.confidence}) as all_rels

            UNWIND all_rels as rel
            WITH
                total_sequences,
                rel.type as seq_type,
                count(rel) as count,
                all_rels

            WITH
                total_sequences,
                collect({type: seq_type, count: count}) as sequence_types,
                all_rels

            UNWIND all_rels as rel

            RETURN
                total_sequences,
                sequence_types,
                avg(rel.confidence) as avg_confidence
            """

            result = session.run(query)
            record = result.single()

            if record:
                return {
                    "total_sequences": record['total_sequences'],
                    "sequence_types": record['sequence_types'],
                    "avg_confidence": record['avg_confidence']
                }

            return {
                "total_sequences": 0,
                "sequence_types": [],
                "avg_confidence": 0.0
            }

    def clear_action_chains(self):
        """Clear all action sequences and entity links"""
        with self.driver.session() as session:
            session.run("MATCH ()-[r:ACTION_SEQUENCE]->() DELETE r")
            session.run("MATCH ()-[r:SAME_ENTITY]-() DELETE r")
            logger.info("Cleared action sequences and entity links")

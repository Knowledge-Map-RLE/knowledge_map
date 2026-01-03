"""
Ontology Generation Service

Generates Ontology nodes from MarkdownAnnotation nodes in Neo4j.
Ontologies are semantic networks combining:
- Syntactic dependencies (nsubj, obj, amod, etc.)
- Semantic relations (IS-A, PART-OF, CAUSES, etc.)

Ontology structure:
- Root node: Ontology with unique ID (ontology_id)
- Properties as separate nodes connected to root via relationships
- Syntactic relationships to other ontologies
- Supports text reconstruction via HAS_WHITESPACE property
"""

from neo4j import GraphDatabase, Session
import json
import uuid
from typing import Generator, Dict, Any
import os
import logging

logger = logging.getLogger(__name__)


class OntologyService:
    def __init__(self):
        neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        neo4j_user = os.getenv("NEO4J_USER", "neo4j")
        neo4j_password = os.getenv("NEO4J_PASSWORD", "password")

        self.driver = GraphDatabase.driver(
            neo4j_uri,
            auth=(neo4j_user, neo4j_password)
        )

    def close(self):
        """Close the Neo4j driver connection"""
        self.driver.close()

    def clear_ontologies(self) -> None:
        """Clear all existing Ontology and OntologyProperty nodes"""
        with self.driver.session() as session:
            session.run("MATCH (o:Ontology) DETACH DELETE o")
            session.run("MATCH (op:OntologyProperty) DELETE op")
            logger.info("Cleared existing Ontology nodes")

    def get_token_count(self) -> int:
        """Get the total number of tokens to process"""
        with self.driver.session() as session:
            query = """
            MATCH (n:MarkdownAnnotation)
            WHERE n.source = 'multilevel_nlp'
            RETURN count(n) as count
            """
            result = session.run(query)
            return result.single()['count']

    def get_ordered_tokens(self) -> list:
        """Get all tokens ordered by sentence and token index"""
        with self.driver.session() as session:
            query = """
            MATCH (n:MarkdownAnnotation)
            WHERE n.source = 'multilevel_nlp'
            RETURN n.uid as uid, n.text as text, properties(n) as props
            ORDER BY
              COALESCE(toInteger(json(n.metadata).sent_idx), 0) ASC,
              COALESCE(toInteger(json(n.metadata).token_idx), 0) ASC
            """
            result = session.run(query)
            tokens = []
            for record in result:
                props = record['props']
                metadata = json.loads(props.get('metadata', '{}'))
                tokens.append({
                    'uid': record['uid'],
                    'text': record['text'],
                    'metadata': metadata,
                    'confidence': props.get('confidence'),
                    'sent_idx': metadata.get('sent_idx'),
                    'token_idx': metadata.get('token_idx')
                })
            return tokens

    def generate_ontologies(
        self,
        batch_size: int = 100,
        clear_existing: bool = True
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Generate ontologies from tokens with progress reporting

        Yields progress updates with:
        - total: total tokens to process
        - processed: number of tokens processed so far
        - percentage: completion percentage
        - stage: current stage (clearing, creating_ontologies, creating_relationships, complete)
        - message: human-readable progress message
        - statistics: final statistics (only in complete stage)

        Args:
            batch_size: Number of tokens to process in each batch
            clear_existing: Whether to clear existing ontologies before generating
        """

        # Clear existing ontologies if requested
        if clear_existing:
            self.clear_ontologies()
            yield {
                "total": 0,
                "processed": 0,
                "percentage": 0,
                "stage": "clearing",
                "message": "Cleared existing ontologies"
            }

        # Get all tokens
        with self.driver.session() as session:
            query = """
            MATCH (n:MarkdownAnnotation)
            WHERE n.source = 'multilevel_nlp'
            RETURN n.uid as uid, n.text as text, properties(n) as props
            """
            tokens = list(session.run(query))
            total_tokens = len(tokens)

        logger.info(f"Found {total_tokens} tokens to process")

        yield {
            "total": total_tokens,
            "processed": 0,
            "percentage": 0,
            "stage": "creating_ontologies",
            "message": f"Found {total_tokens} tokens"
        }

        # Process tokens in batches
        for batch_start in range(0, total_tokens, batch_size):
            batch_end = min(batch_start + batch_size, total_tokens)
            batch_tokens = tokens[batch_start:batch_end]

            # Prepare batch data
            ontologies_data = []
            for token_record in batch_tokens:
                token_uid = token_record['uid']
                props = token_record['props']
                metadata = json.loads(props.get('metadata', '{}'))

                ontology_id = str(uuid.uuid4())

                ontology_data = {
                    'ontology_id': ontology_id,
                    'source_token_uid': token_uid,
                    'text': props.get('text', ''),
                    'lemma': metadata.get('lemma'),
                    'pos': metadata.get('pos'),
                    'pos_fine': metadata.get('pos_fine'),
                    'confidence': props.get('confidence'),
                    'morph': metadata.get('morph', {}),
                    'sent_idx': metadata.get('sent_idx'),
                    'token_idx': metadata.get('token_idx'),
                    'whitespace_after': metadata.get('whitespace_after', ' ')
                }

                ontologies_data.append(ontology_data)

            # Create ontologies and properties in batch
            self._create_batch_ontologies(ontologies_data)

            processed = batch_end
            percentage = int((processed / total_tokens) * 100)

            yield {
                "total": total_tokens,
                "processed": processed,
                "percentage": percentage,
                "stage": "creating_ontologies",
                "message": f"Created ontologies {batch_start + 1}-{batch_end}/{total_tokens}"
            }

        # Create syntactic relationships
        yield {
            "total": total_tokens,
            "processed": total_tokens,
            "percentage": 100,
            "stage": "creating_relationships",
            "message": "Creating syntactic relationships..."
        }

        rel_count = self._create_syntactic_relationships()
        logger.info(f"Created {rel_count} syntactic relationships")

        # Get final statistics
        stats = self._get_statistics()

        yield {
            "total": total_tokens,
            "processed": total_tokens,
            "percentage": 100,
            "stage": "complete",
            "message": "Ontology generation complete",
            "statistics": stats
        }

    def _create_batch_ontologies(self, ontologies_data: list) -> None:
        """Create a batch of ontologies with all their properties"""
        with self.driver.session() as session:
            # Create Ontology nodes with indices and concept_type
            session.run("""
                UNWIND $ontologies_data AS ontology
                CREATE (o:Ontology {
                    ontology_id: ontology.ontology_id,
                    source_token_uid: ontology.source_token_uid,
                    concept_type: 'token',
                    sent_idx: CASE
                        WHEN ontology.sent_idx IS NOT NULL THEN toInteger(ontology.sent_idx)
                        ELSE 0
                    END,
                    token_idx: CASE
                        WHEN ontology.token_idx IS NOT NULL THEN toInteger(ontology.token_idx)
                        ELSE 0
                    END,
                    created_at: timestamp()
                })
            """, ontologies_data=ontologies_data)

            # Create TEXT properties
            session.run("""
                UNWIND $ontologies_data AS ontology
                MATCH (o:Ontology {ontology_id: ontology.ontology_id})
                CREATE (prop:OntologyProperty {type: 'text', value: ontology.text})
                CREATE (o)-[:HAS_TEXT]->(prop)
            """, ontologies_data=ontologies_data)

            # Create WHITESPACE properties (for text reconstruction)
            session.run("""
                UNWIND $ontologies_data AS ontology
                MATCH (o:Ontology {ontology_id: ontology.ontology_id})
                CREATE (prop:OntologyProperty {
                  type: 'whitespace',
                  value: ontology.whitespace_after
                })
                CREATE (o)-[:HAS_WHITESPACE]->(prop)
            """, ontologies_data=ontologies_data)

            # Create LEMMA properties
            lemma_data = [p for p in ontologies_data if p['lemma']]
            if lemma_data:
                session.run("""
                    UNWIND $ontologies_data AS ontology
                    MATCH (o:Ontology {ontology_id: ontology.ontology_id})
                    CREATE (prop:OntologyProperty {type: 'lemma', value: ontology.lemma})
                    CREATE (o)-[:HAS_LEMMA]->(prop)
                """, ontologies_data=lemma_data)

            # Create POS properties
            pos_data = [p for p in ontologies_data if p['pos']]
            if pos_data:
                session.run("""
                    UNWIND $ontologies_data AS ontology
                    MATCH (o:Ontology {ontology_id: ontology.ontology_id})
                    CREATE (prop:OntologyProperty {type: 'pos', value: ontology.pos})
                    CREATE (o)-[:HAS_POS]->(prop)
                """, ontologies_data=pos_data)

            # Create POS_FINE properties
            pos_fine_data = [p for p in ontologies_data if p['pos_fine']]
            if pos_fine_data:
                session.run("""
                    UNWIND $ontologies_data AS ontology
                    MATCH (o:Ontology {ontology_id: ontology.ontology_id})
                    CREATE (prop:OntologyProperty {type: 'pos_fine', value: ontology.pos_fine})
                    CREATE (o)-[:HAS_POS_FINE]->(prop)
                """, ontologies_data=pos_fine_data)

            # Create CONFIDENCE properties
            conf_data = [p for p in ontologies_data if p['confidence'] is not None]
            if conf_data:
                session.run("""
                    UNWIND $ontologies_data AS ontology
                    MATCH (o:Ontology {ontology_id: ontology.ontology_id})
                    CREATE (prop:OntologyProperty {type: 'confidence', value: ontology.confidence})
                    CREATE (o)-[:HAS_CONFIDENCE]->(prop)
                """, ontologies_data=conf_data)

            # Create MORPH properties
            morph_data = []
            for ontology in ontologies_data:
                if ontology['morph']:
                    for morph_key, morph_val in ontology['morph'].items():
                        morph_data.append({
                            'ontology_id': ontology['ontology_id'],
                            'key': morph_key,
                            'value': morph_val
                        })

            if morph_data:
                session.run("""
                    UNWIND $morph_data AS morph
                    MATCH (o:Ontology {ontology_id: morph.ontology_id})
                    CREATE (prop:OntologyProperty {type: 'morph', key: morph.key, value: morph.value})
                    CREATE (o)-[:HAS_MORPH]->(prop)
                """, morph_data=morph_data)

    def _create_syntactic_relationships(self) -> int:
        """
        Create syntactic relationships between ontologies.
        These are based on the original RELATES_TO relationships from MarkdownAnnotation nodes.
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH (o1:Ontology)
                MATCH (o2:Ontology)
                MATCH (t1:MarkdownAnnotation {uid: o1.source_token_uid})
                MATCH (t2:MarkdownAnnotation {uid: o2.source_token_uid})
                MATCH (t1)-[r:RELATES_TO]->(t2)
                WHERE o1.ontology_id <> o2.ontology_id
                WITH o1, o2, r
                CREATE (o1)-[rel:SYNTACTIC_RELATION {
                    relation_type: r.relation_type,
                    dependency_label: r.relation_type,
                    confidence: 1.0,
                    created_at: timestamp()
                }]->(o2)
                RETURN count(rel) as count
            """)
            return result.single()['count']

    def _get_statistics(self) -> Dict[str, int]:
        """Get statistics about generated ontologies"""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (o:Ontology)
                WITH count(o) as ontology_count
                MATCH (prop:OntologyProperty)
                WITH ontology_count, count(prop) as prop_count
                MATCH ()-[r:SYNTACTIC_RELATION]->()
                RETURN ontology_count, prop_count, count(r) as rel_count
            """)
            record = result.single()
            return {
                "ontologies": record['ontology_count'],
                "properties": record['prop_count'],
                "relationships": record['rel_count']
            }

    def get_ontologies_by_document(self, document_uid: str) -> list:
        """Get all ontologies for a specific document"""
        with self.driver.session() as session:
            query = """
            MATCH (doc:PDFDocument {uid: $doc_uid})
            MATCH (doc)-[:HAS_MARKDOWN_ANNOTATION]->(ann:MarkdownAnnotation)
            MATCH (o:Ontology {source_token_uid: ann.uid})
            RETURN o.ontology_id as ontology_id,
                   o.sent_idx as sent_idx,
                   o.token_idx as token_idx,
                   o.concept_type as concept_type
            ORDER BY o.sent_idx ASC, o.token_idx ASC
            """
            result = session.run(query, doc_uid=document_uid)
            return list(result)

    def get_ontology_with_properties(self, ontology_id: str) -> Dict[str, Any]:
        """Get a single ontology with all its properties"""
        with self.driver.session() as session:
            query = """
            MATCH (o:Ontology {ontology_id: $ontology_id})
            OPTIONAL MATCH (o)-[r]-(prop:OntologyProperty)
            RETURN {
                ontology_id: o.ontology_id,
                source_token_uid: o.source_token_uid,
                concept_type: o.concept_type,
                sent_idx: o.sent_idx,
                token_idx: o.token_idx,
                created_at: o.created_at,
                properties: COLLECT(DISTINCT {
                    type: prop.type,
                    value: prop.value,
                    key: CASE WHEN prop.key IS NOT NULL THEN prop.key ELSE null END
                })
            } as ontology
            """
            result = session.run(query, ontology_id=ontology_id)
            record = result.single()
            return record['ontology'] if record else None

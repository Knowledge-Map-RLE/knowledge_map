"""
Pattern Generation Service

Generates Pattern nodes from MarkdownAnnotation nodes in Neo4j.
Pattern structure:
- Root node: Pattern with unique ID
- Properties as separate nodes connected to root
- Linguistic relationships to other patterns
"""

from neo4j import GraphDatabase, Session
import json
import uuid
from typing import Generator, Dict, Any
import os
import logging

logger = logging.getLogger(__name__)


class PatternService:
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

    def clear_patterns(self) -> None:
        """Clear all existing Pattern and PatternProperty nodes"""
        with self.driver.session() as session:
            session.run("MATCH (p:Pattern) DETACH DELETE p")
            session.run("MATCH (p:PatternProperty) DELETE p")
            logger.info("Cleared existing Pattern nodes")

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

    def generate_patterns(
        self,
        batch_size: int = 100,
        clear_existing: bool = True
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Generate patterns from tokens with progress reporting

        Yields progress updates with:
        - total: total tokens to process
        - processed: number of tokens processed so far
        - percentage: completion percentage
        - stage: current stage (creating_patterns, creating_relationships, complete)
        """

        # Clear existing patterns if requested
        if clear_existing:
            self.clear_patterns()
            yield {
                "total": 0,
                "processed": 0,
                "percentage": 0,
                "stage": "clearing",
                "message": "Cleared existing patterns"
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
            "stage": "creating_patterns",
            "message": f"Found {total_tokens} tokens"
        }

        # Process tokens in batches
        for batch_start in range(0, total_tokens, batch_size):
            batch_end = min(batch_start + batch_size, total_tokens)
            batch_tokens = tokens[batch_start:batch_end]

            # Prepare batch data
            patterns_data = []
            for token_record in batch_tokens:
                token_uid = token_record['uid']
                props = token_record['props']
                metadata = json.loads(props.get('metadata', '{}'))

                pattern_id = str(uuid.uuid4())

                pattern_data = {
                    'pattern_id': pattern_id,
                    'source_token_uid': token_uid,
                    'text': props.get('text', ''),
                    'lemma': metadata.get('lemma'),
                    'pos': metadata.get('pos'),
                    'pos_fine': metadata.get('pos_fine'),
                    'confidence': props.get('confidence'),
                    'morph': metadata.get('morph', {})
                }

                patterns_data.append(pattern_data)

            # Create patterns and properties in batch
            self._create_batch_patterns(patterns_data)

            processed = batch_end
            percentage = int((processed / total_tokens) * 100)

            yield {
                "total": total_tokens,
                "processed": processed,
                "percentage": percentage,
                "stage": "creating_patterns",
                "message": f"Created patterns {batch_start + 1}-{batch_end}/{total_tokens}"
            }

        # Create linguistic relationships
        yield {
            "total": total_tokens,
            "processed": total_tokens,
            "percentage": 100,
            "stage": "creating_relationships",
            "message": "Creating linguistic relationships..."
        }

        rel_count = self._create_linguistic_relationships()

        # Get final statistics
        stats = self._get_statistics()

        yield {
            "total": total_tokens,
            "processed": total_tokens,
            "percentage": 100,
            "stage": "complete",
            "message": "Pattern generation complete",
            "statistics": stats
        }

    def _create_batch_patterns(self, patterns_data: list) -> None:
        """Create a batch of patterns with all their properties"""
        with self.driver.session() as session:
            # Create Pattern nodes
            session.run("""
                UNWIND $patterns_data AS pattern
                CREATE (p:Pattern {
                    pattern_id: pattern.pattern_id,
                    source_token_uid: pattern.source_token_uid,
                    created_at: timestamp()
                })
            """, patterns_data=patterns_data)

            # Create TEXT properties
            session.run("""
                UNWIND $patterns_data AS pattern
                MATCH (p:Pattern {pattern_id: pattern.pattern_id})
                CREATE (prop:PatternProperty {type: 'text', value: pattern.text})
                CREATE (p)-[:HAS_TEXT]->(prop)
            """, patterns_data=patterns_data)

            # Create LEMMA properties
            lemma_data = [p for p in patterns_data if p['lemma']]
            if lemma_data:
                session.run("""
                    UNWIND $patterns_data AS pattern
                    MATCH (p:Pattern {pattern_id: pattern.pattern_id})
                    CREATE (prop:PatternProperty {type: 'lemma', value: pattern.lemma})
                    CREATE (p)-[:HAS_LEMMA]->(prop)
                """, patterns_data=lemma_data)

            # Create POS properties
            pos_data = [p for p in patterns_data if p['pos']]
            if pos_data:
                session.run("""
                    UNWIND $patterns_data AS pattern
                    MATCH (p:Pattern {pattern_id: pattern.pattern_id})
                    CREATE (prop:PatternProperty {type: 'pos', value: pattern.pos})
                    CREATE (p)-[:HAS_POS]->(prop)
                """, patterns_data=pos_data)

            # Create POS_FINE properties
            pos_fine_data = [p for p in patterns_data if p['pos_fine']]
            if pos_fine_data:
                session.run("""
                    UNWIND $patterns_data AS pattern
                    MATCH (p:Pattern {pattern_id: pattern.pattern_id})
                    CREATE (prop:PatternProperty {type: 'pos_fine', value: pattern.pos_fine})
                    CREATE (p)-[:HAS_POS_FINE]->(prop)
                """, patterns_data=pos_fine_data)

            # Create CONFIDENCE properties
            conf_data = [p for p in patterns_data if p['confidence'] is not None]
            if conf_data:
                session.run("""
                    UNWIND $patterns_data AS pattern
                    MATCH (p:Pattern {pattern_id: pattern.pattern_id})
                    CREATE (prop:PatternProperty {type: 'confidence', value: pattern.confidence})
                    CREATE (p)-[:HAS_CONFIDENCE]->(prop)
                """, patterns_data=conf_data)

            # Create MORPH properties
            morph_data = []
            for pattern in patterns_data:
                if pattern['morph']:
                    for morph_key, morph_val in pattern['morph'].items():
                        morph_data.append({
                            'pattern_id': pattern['pattern_id'],
                            'key': morph_key,
                            'value': morph_val
                        })

            if morph_data:
                session.run("""
                    UNWIND $morph_data AS morph
                    MATCH (p:Pattern {pattern_id: morph.pattern_id})
                    CREATE (prop:PatternProperty {type: 'morph', key: morph.key, value: morph.value})
                    CREATE (p)-[:HAS_MORPH]->(prop)
                """, morph_data=morph_data)

    def _create_linguistic_relationships(self) -> int:
        """Create linguistic relationships between patterns"""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (p1:Pattern)
                MATCH (p2:Pattern)
                MATCH (t1:MarkdownAnnotation {uid: p1.source_token_uid})
                MATCH (t2:MarkdownAnnotation {uid: p2.source_token_uid})
                MATCH (t1)-[r:RELATES_TO]->(t2)
                WHERE p1.pattern_id <> p2.pattern_id
                WITH p1, p2, r
                CREATE (p1)-[rel:LINGUISTIC_RELATION {
                    relation_type: r.relation_type,
                    created_at: timestamp()
                }]->(p2)
                RETURN count(rel) as count
            """)
            return result.single()['count']

    def _get_statistics(self) -> Dict[str, int]:
        """Get statistics about generated patterns"""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (p:Pattern)
                WITH count(p) as pattern_count
                MATCH (prop:PatternProperty)
                WITH pattern_count, count(prop) as prop_count
                MATCH ()-[r:LINGUISTIC_RELATION]->()
                RETURN pattern_count, prop_count, count(r) as rel_count
            """)
            record = result.single()
            return {
                "patterns": record['pattern_count'],
                "properties": record['prop_count'],
                "relationships": record['rel_count']
            }

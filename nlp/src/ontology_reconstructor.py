"""
Ontology Text Reconstructor

Reconstructs original text from Ontology graph representation.

Algorithm (Phase 1 - Simple):
1. Query all Ontology nodes ordered by (sent_idx, token_idx)
2. For each node:
   - Get original text from HAS_TEXT property
   - Get whitespace from HAS_WHITESPACE property
   - Append: text + whitespace
3. Return concatenated string

This simple algorithm works because:
- Original text forms are preserved (not lemmas)
- Whitespace is stored explicitly
- Token order is preserved via indices
"""

from typing import List, Dict, Any, Optional, Tuple
from neo4j import GraphDatabase
import os
import logging
from dataclasses import dataclass
import Levenshtein

logger = logging.getLogger(__name__)


@dataclass
class ReconstructionMetrics:
    """Metrics for evaluating reconstruction quality"""
    char_accuracy: float  # % correct characters
    word_accuracy: float  # % correct words
    edit_distance: int    # Levenshtein distance
    bleu_score: float     # BLEU translation metric
    is_exact_match: bool  # Perfect reconstruction


class OntologyReconstructor:
    """
    Reconstructs original text from Ontology graph.
    """

    def __init__(self):
        neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        neo4j_user = os.getenv("NEO4J_USER", "neo4j")
        neo4j_password = os.getenv("NEO4J_PASSWORD", "password")

        self.driver = GraphDatabase.driver(
            neo4j_uri,
            auth=(neo4j_user, neo4j_password)
        )

    def close(self):
        """Close Neo4j driver connection"""
        self.driver.close()

    def reconstruct_text_from_ontology(
        self,
        document_uid: Optional[str] = None
    ) -> str:
        """
        Reconstruct text from ontology graph.

        Algorithm:
        1. Query all Ontology nodes ordered by (sent_idx, token_idx)
        2. For each node, get HAS_TEXT and HAS_WHITESPACE
        3. Concatenate: text + whitespace

        Args:
            document_uid: Optional filter for specific document

        Returns:
            Reconstructed text string
        """
        with self.driver.session() as session:
            query = """
            MATCH (o:Ontology)-[:HAS_TEXT]->(text:OntologyProperty {type: 'text'})
            MATCH (o)-[:HAS_WHITESPACE]->(ws:OntologyProperty {type: 'whitespace'})
            WHERE o.concept_type = 'token'
            """

            if document_uid:
                query += """
                AND EXISTS {
                    MATCH (doc:PDFDocument {uid: $document_uid})
                    MATCH (doc)-[:HAS_MARKDOWN_ANNOTATION]->(ann:MarkdownAnnotation {uid: o.source_token_uid})
                }
                """

            query += """
            RETURN
                o.sent_idx as sent_idx,
                o.token_idx as token_idx,
                text.value as text,
                ws.value as whitespace
            ORDER BY o.sent_idx ASC, o.token_idx ASC
            """

            params = {}
            if document_uid:
                params['document_uid'] = document_uid

            result = session.run(query, params)

            # Reconstruct text
            reconstructed_parts = []
            records = list(result)

            if not records:
                logger.warning("No ontology nodes found for reconstruction")
                return ""

            for record in records:
                text = record['text']
                whitespace = record['whitespace']
                reconstructed_parts.append(text + whitespace)

            reconstructed = ''.join(reconstructed_parts)
            # Remove trailing whitespace
            return reconstructed.rstrip()

    def reconstruct_token(self, ontology_id: str) -> Optional[str]:
        """
        Reconstruct a single token's text form.

        Args:
            ontology_id: UUID of Ontology node

        Returns:
            Text value of the token, or None if not found
        """
        with self.driver.session() as session:
            query = """
            MATCH (o:Ontology {ontology_id: $ontology_id})
            MATCH (o)-[:HAS_TEXT]->(text:OntologyProperty {type: 'text'})
            RETURN text.value as text
            """

            result = session.run(query, ontology_id=ontology_id)
            record = result.single()

            if record:
                return record['text']
            return None

    def get_all_tokens(self, document_uid: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all tokens from ontology in order.

        Args:
            document_uid: Optional filter for specific document

        Returns:
            List of token dictionaries with text, whitespace, and metadata
        """
        with self.driver.session() as session:
            query = """
            MATCH (o:Ontology)-[:HAS_TEXT]->(text:OntologyProperty {type: 'text'})
            MATCH (o)-[:HAS_WHITESPACE]->(ws:OntologyProperty {type: 'whitespace'})
            WHERE o.concept_type = 'token'
            """

            if document_uid:
                query += """
                AND EXISTS {
                    MATCH (doc:PDFDocument {uid: $document_uid})
                    MATCH (doc)-[:HAS_MARKDOWN_ANNOTATION]->(ann:MarkdownAnnotation {uid: o.source_token_uid})
                }
                """

            query += """
            RETURN
                o.ontology_id as ontology_id,
                o.sent_idx as sent_idx,
                o.token_idx as token_idx,
                o.source_token_uid as source_token_uid,
                text.value as text,
                ws.value as whitespace
            ORDER BY o.sent_idx ASC, o.token_idx ASC
            """

            params = {}
            if document_uid:
                params['document_uid'] = document_uid

            result = session.run(query, params)

            tokens = []
            for record in result:
                tokens.append({
                    'ontology_id': record['ontology_id'],
                    'sent_idx': record['sent_idx'],
                    'token_idx': record['token_idx'],
                    'source_token_uid': record['source_token_uid'],
                    'text': record['text'],
                    'whitespace': record['whitespace']
                })

            return tokens

    def compute_reconstruction_metrics(
        self,
        original: str,
        reconstructed: str
    ) -> ReconstructionMetrics:
        """
        Compute metrics for reconstruction quality.

        Metrics:
        - Character accuracy: % characters correct
        - Word accuracy: % words correct
        - Levenshtein distance: edit distance
        - BLEU score: translation quality metric

        Args:
            original: Original text
            reconstructed: Reconstructed text

        Returns:
            ReconstructionMetrics dataclass
        """

        # Character accuracy
        char_correct = sum(
            1 for a, b in zip(original, reconstructed) if a == b
        )
        char_accuracy = char_correct / len(original) if original else 0.0

        # Word accuracy
        orig_words = original.split()
        recon_words = reconstructed.split()
        word_correct = sum(
            1 for a, b in zip(orig_words, recon_words) if a == b
        )
        word_accuracy = word_correct / len(orig_words) if orig_words else 0.0

        # Levenshtein distance (edit distance)
        edit_distance = Levenshtein.distance(original, reconstructed)

        # BLEU score
        bleu = self._compute_bleu_score(orig_words, recon_words)

        # Exact match
        is_exact = original == reconstructed

        return ReconstructionMetrics(
            char_accuracy=char_accuracy,
            word_accuracy=word_accuracy,
            edit_distance=edit_distance,
            bleu_score=bleu,
            is_exact_match=is_exact
        )

    def _compute_bleu_score(
        self,
        reference: List[str],
        hypothesis: List[str]
    ) -> float:
        """
        Compute simple BLEU score (n-gram overlap).

        This is a simplified version of BLEU score.
        Full implementation would use nltk.translate.bleu_score.

        Args:
            reference: Reference token list
            hypothesis: Hypothesis token list

        Returns:
            BLEU score (0.0 to 1.0)
        """
        try:
            from nltk.translate.bleu_score import sentence_bleu, SmoothingFunction
            smoothing = SmoothingFunction().method1
            return sentence_bleu([reference], hypothesis, smoothing_function=smoothing)
        except ImportError:
            # Fallback: simple 1-gram overlap
            if not reference:
                return 1.0 if not hypothesis else 0.0

            overlap = len(set(reference) & set(hypothesis))
            return overlap / len(set(reference)) if set(reference) else 0.0

    def get_token_sequence(
        self,
        document_uid: Optional[str] = None
    ) -> List[Tuple[str, str]]:
        """
        Get sequence of (text, whitespace) tuples.

        Args:
            document_uid: Optional filter for specific document

        Returns:
            List of (text, whitespace) tuples in order
        """
        tokens = self.get_all_tokens(document_uid)
        return [(token['text'], token['whitespace']) for token in tokens]

    def validate_reconstruction_integrity(
        self,
        original: str,
        document_uid: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Validate that the ontology can be reconstructed correctly.

        This checks:
        1. All tokens are present
        2. Token order is correct (sent_idx, token_idx)
        3. Whitespace is preserved
        4. Special characters (punctuation) are handled
        5. Text reconstruction matches original

        Args:
            original: Original text
            document_uid: Optional document filter

        Returns:
            Validation report with status and issues
        """
        reconstructed = self.reconstruct_text_from_ontology(document_uid)
        metrics = self.compute_reconstruction_metrics(original, reconstructed)

        issues = []

        if not metrics.is_exact_match:
            issues.append({
                'type': 'inexact_match',
                'severity': 'error',
                'message': f'Reconstruction does not match original',
                'details': {
                    'char_accuracy': metrics.char_accuracy,
                    'word_accuracy': metrics.word_accuracy,
                    'edit_distance': metrics.edit_distance
                }
            })

        tokens = self.get_all_tokens(document_uid)
        if not tokens:
            issues.append({
                'type': 'no_tokens',
                'severity': 'error',
                'message': 'No tokens found in ontology'
            })

        # Check for missing indices
        for i, token in enumerate(tokens):
            if token['sent_idx'] is None or token['token_idx'] is None:
                issues.append({
                    'type': 'missing_indices',
                    'severity': 'error',
                    'message': f'Token {i} is missing sent_idx or token_idx',
                    'token_id': token['ontology_id']
                })

        return {
            'is_valid': len(issues) == 0,
            'metrics': {
                'char_accuracy': metrics.char_accuracy,
                'word_accuracy': metrics.word_accuracy,
                'edit_distance': metrics.edit_distance,
                'bleu_score': metrics.bleu_score,
                'is_exact_match': metrics.is_exact_match
            },
            'token_count': len(tokens),
            'issues': issues
        }

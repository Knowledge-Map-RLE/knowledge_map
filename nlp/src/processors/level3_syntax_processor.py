"""
Level 3 Processor: Syntax and Dependency Parsing

Extends Level 2 with syntactic dependency analysis.
Combines spaCy dependency parser with voting.
"""

from typing import List, Optional, Dict, Any, Tuple
import spacy
import networkx as nx

from src.adapters.spacy_adapter import SpacyAdapter
from src.voting.voting_engine import VotingEngine
from src.unified_types import (
    UnifiedToken,
    UnifiedDependency,
    UnifiedSentence,
    UnifiedDocument,
    UnifiedPhrase,
    LinguisticLevel,
)
from src.processors.level2_morphology_processor import Level2MorphologyProcessor


class Level3SyntaxProcessor(Level2MorphologyProcessor):
    """
    Syntax and dependency parsing processor with voting.

    Inherits from Level2 and adds dependency analysis.
    """

    def __init__(
        self,
        spacy_model: str = "en_core_sci_lg",
        enable_voting: bool = True,
        min_agreement: int = 1,
    ):
        """Initialize Level 3 processor."""
        super().__init__(
            spacy_model=spacy_model,
            enable_voting=enable_voting,
            min_agreement=min_agreement
        )

    # ============================================================================
    # BaseNLPProcessor interface implementation
    # ============================================================================

    def get_level(self) -> LinguisticLevel:
        """Get the linguistic level this processor handles."""
        return LinguisticLevel.SYNTAX

    # ============================================================================
    # Main processing methods (override)
    # ============================================================================

    def process(self, text: str) -> UnifiedDocument:
        """
        Process text through Level 3 (tokenization + morphology + syntax).

        Args:
            text: Input text

        Returns:
            UnifiedDocument with tokens, morphology, and dependencies
        """
        # Run Level 2
        doc = super().process(text)

        # Dependencies are already extracted by adapters in Level 1
        # Just add phrases and update processed levels
        doc = self._add_phrases(doc)
        doc.processed_levels.append(LinguisticLevel.SYNTAX)

        return doc

    def _add_phrases(self, doc: UnifiedDocument) -> UnifiedDocument:
        """
        Add phrase structures to document using spaCy noun chunks.

        Args:
            doc: Unified document

        Returns:
            Document with added phrases
        """
        # Re-process with spaCy to get phrases
        spacy_doc = self.spacy_nlp(doc.text)

        for sent_idx, (sent, spacy_sent) in enumerate(zip(doc.sentences, spacy_doc.sents)):
            # Extract noun chunks
            phrases = self.spacy_adapter.extract_noun_chunks(spacy_sent, sent.tokens)
            sent.phrases.extend(phrases)

            # Extract verb phrases (simple heuristic)
            verb_phrases = self.spacy_adapter.extract_verb_phrases(spacy_sent, sent.tokens)
            sent.phrases.extend(verb_phrases)

        return doc

    # ============================================================================
    # Dependency analysis methods
    # ============================================================================

    def get_dependency_statistics(self, doc: UnifiedDocument) -> Dict[str, Any]:
        """
        Get statistics about dependencies.

        Args:
            doc: Unified document

        Returns:
            Dictionary with statistics
        """
        # Count dependency relations
        dep_counts = {}
        total_deps = 0

        for sent in doc.sentences:
            total_deps += len(sent.dependencies)

            for dep in sent.dependencies:
                dep_counts[dep.relation] = dep_counts.get(dep.relation, 0) + 1

        # Get top relations
        top_deps = sorted(dep_counts.items(), key=lambda x: x[1], reverse=True)[:15]

        stats = {
            'total_dependencies': total_deps,
            'dependency_distribution': dict(top_deps),
            'unique_dependency_types': len(dep_counts),
        }

        # Add Level 2 stats
        stats.update(self.get_morphology_statistics(doc))

        return stats

    def build_dependency_tree(self, sentence: UnifiedSentence) -> nx.DiGraph:
        """
        Build dependency tree as NetworkX directed graph.

        Args:
            sentence: Unified sentence

        Returns:
            NetworkX DiGraph
        """
        G = nx.DiGraph()

        # Add nodes (tokens)
        for token in sentence.tokens:
            G.add_node(
                token.idx,
                text=token.text,
                pos=token.pos,
                lemma=token.lemma
            )

        # Add edges (dependencies)
        for dep in sentence.dependencies:
            G.add_edge(
                dep.head_idx,
                dep.dependent_idx,
                relation=dep.relation,
                confidence=dep.confidence
            )

        return G

    def get_syntactic_head(self, sentence: UnifiedSentence) -> Optional[UnifiedToken]:
        """
        Get syntactic head (root) of sentence.

        Args:
            sentence: Unified sentence

        Returns:
            Root token or None
        """
        if sentence.root_idx is not None:
            for token in sentence.tokens:
                if token.idx == sentence.root_idx:
                    return token
        return None

    def get_dependents(
        self,
        sentence: UnifiedSentence,
        head_token: UnifiedToken
    ) -> List[Tuple[UnifiedToken, str]]:
        """
        Get all dependents of a head token.

        Args:
            sentence: Unified sentence
            head_token: Head token

        Returns:
            List of (dependent_token, relation) tuples
        """
        dependents = []

        for dep in sentence.dependencies:
            if dep.head_idx == head_token.idx:
                # Find dependent token
                for token in sentence.tokens:
                    if token.idx == dep.dependent_idx:
                        dependents.append((token, dep.relation))
                        break

        return dependents

    def get_subtree(
        self,
        sentence: UnifiedSentence,
        head_token: UnifiedToken
    ) -> List[UnifiedToken]:
        """
        Get all tokens in subtree rooted at head_token.

        Args:
            sentence: Unified sentence
            head_token: Head token

        Returns:
            List of tokens in subtree (including head)
        """
        # Build dependency graph
        G = self.build_dependency_tree(sentence)

        # Get descendants
        try:
            descendants = nx.descendants(G, head_token.idx)
            descendant_tokens = [head_token]

            for token in sentence.tokens:
                if token.idx in descendants:
                    descendant_tokens.append(token)

            return descendant_tokens

        except nx.NetworkXError:
            # Node not in graph
            return [head_token]

    def find_subject_verb_object(
        self,
        sentence: UnifiedSentence
    ) -> Dict[str, Optional[UnifiedToken]]:
        """
        Find subject, verb, and object in sentence.

        Args:
            sentence: Unified sentence

        Returns:
            Dictionary with 'subject', 'verb', 'object' keys
        """
        result = {
            'subject': None,
            'verb': None,
            'object': None,
        }

        # Find main verb (root)
        verb = self.get_syntactic_head(sentence)
        if verb and verb.pos == 'VERB':
            result['verb'] = verb

            # Find subject and object
            for dep in sentence.dependencies:
                if dep.head_idx == verb.idx:
                    # Subject
                    if dep.relation in ['nsubj', 'nsubj:pass', 'csubj']:
                        for token in sentence.tokens:
                            if token.idx == dep.dependent_idx:
                                result['subject'] = token
                                break

                    # Object
                    elif dep.relation in ['obj', 'dobj', 'iobj']:
                        for token in sentence.tokens:
                            if token.idx == dep.dependent_idx:
                                result['object'] = token
                                break

        return result

    def extract_clauses(self, sentence: UnifiedSentence) -> List[Dict[str, Any]]:
        """
        Extract clauses from sentence.

        A clause is a unit with a verb and its dependents.

        Args:
            sentence: Unified sentence

        Returns:
            List of clause dictionaries
        """
        clauses = []

        # Find all verbs
        for token in sentence.tokens:
            if token.pos == 'VERB':
                # Get verb's subtree
                subtree = self.get_subtree(sentence, token)

                # Get dependents
                dependents = self.get_dependents(sentence, token)

                clause = {
                    'verb': token.text,
                    'verb_lemma': token.lemma,
                    'tokens': [t.text for t in subtree],
                    'dependents': [
                        {'text': t.text, 'relation': rel}
                        for t, rel in dependents
                    ],
                }
                clauses.append(clause)

        return clauses

    # ============================================================================
    # Phrase extraction
    # ============================================================================

    def get_noun_phrases(self, doc: UnifiedDocument) -> List[str]:
        """
        Get all noun phrases in document.

        Args:
            doc: Unified document

        Returns:
            List of noun phrase texts
        """
        noun_phrases = []

        for sent in doc.sentences:
            for phrase in sent.phrases:
                if phrase.phrase_type == 'NP':
                    noun_phrases.append(phrase.text())

        return noun_phrases

    def get_verb_phrases(self, doc: UnifiedDocument) -> List[str]:
        """
        Get all verb phrases in document.

        Args:
            doc: Unified document

        Returns:
            List of verb phrase texts
        """
        verb_phrases = []

        for sent in doc.sentences:
            for phrase in sent.phrases:
                if phrase.phrase_type == 'VP':
                    verb_phrases.append(phrase.text())

        return verb_phrases

    # ============================================================================
    # Syntactic patterns
    # ============================================================================

    def find_dependency_patterns(
        self,
        doc: UnifiedDocument,
        pattern: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Find sentences matching a dependency pattern.

        Args:
            doc: Unified document
            pattern: List of dependency relations (e.g., ['nsubj', 'obj'])

        Returns:
            List of matching sentences with matched dependencies
        """
        matches = []

        for sent in doc.sentences:
            # Get dependency relations in this sentence
            sent_relations = [dep.relation for dep in sent.dependencies]

            # Check if pattern is subset
            if all(rel in sent_relations for rel in pattern):
                matches.append({
                    'sentence': sent.text,
                    'dependencies': [
                        {
                            'relation': dep.relation,
                            'head': sent.tokens[dep.head_idx].text,
                            'dependent': sent.tokens[dep.dependent_idx].text,
                        }
                        for dep in sent.dependencies
                        if dep.relation in pattern
                    ]
                })

        return matches

    # ============================================================================
    # BaseNLPProcessor interface implementation
    # ============================================================================

    def process_text(self, text: str, **kwargs) -> Dict[str, Any]:
        """Process text (BaseNLPProcessor interface)."""
        doc = self.process(text)

        # Convert to dict format with syntax
        result = {
            'sentences': [],
            'statistics': self.get_dependency_statistics(doc),
            'noun_phrases': self.get_noun_phrases(doc),
            'verb_phrases': self.get_verb_phrases(doc),
            'metadata': doc.metadata,
        }

        for sent in doc.sentences:
            # Get SVO structure
            svo = self.find_subject_verb_object(sent)

            sent_data = {
                'text': sent.text,
                'tokens': [
                    {
                        'text': token.text,
                        'pos': token.pos,
                        'lemma': token.lemma,
                        'morph': token.morph,
                        'confidence': token.confidence,
                        'sources': token.sources,
                    }
                    for token in sent.tokens
                ],
                'dependencies': [
                    {
                        'relation': dep.relation,
                        'head': sent.tokens[dep.head_idx].text if dep.head_idx < len(sent.tokens) else None,
                        'dependent': sent.tokens[dep.dependent_idx].text if dep.dependent_idx < len(sent.tokens) else None,
                        'confidence': dep.confidence,
                        'sources': dep.sources,
                    }
                    for dep in sent.dependencies
                ],
                'subject': svo['subject'].text if svo['subject'] else None,
                'verb': svo['verb'].text if svo['verb'] else None,
                'object': svo['object'].text if svo['object'] else None,
                'clauses': self.extract_clauses(sent),
            }
            result['sentences'].append(sent_data)

        return result

    def get_supported_types(self) -> List[str]:
        """Get supported annotation types."""
        return ['TOKEN', 'SENTENCE', 'POS', 'MORPHOLOGY', 'DEPENDENCY', 'PHRASE', 'CLAUSE']

    def get_processor_info(self) -> Dict[str, Any]:
        """Get processor information."""
        info = super().get_processor_info()
        info.update({
            'level': 3,
            'name': 'Level3SyntaxProcessor',
            'description': 'Multi-tool syntax and dependency parsing with voting',
        })
        return info

"""
Multi-level NLP service for Knowledge Map.

Provides advanced linguistic analysis with voting and confidence scores.
"""

import asyncio
from typing import List, Dict, Any, Optional
import logging

from services.nlp_grpc_client import get_nlp_grpc_client

logger = logging.getLogger(__name__)


class UnifiedDocumentWrapper:
    """
    Обертка для UnifiedDocument из gRPC ответа.
    Имитирует интерфейс UnifiedDocument для совместимости с существующим кодом.
    """
    
    def __init__(self, doc_dict: Dict[str, Any]):
        """Инициализация из словаря, полученного из gRPC"""
        self.text = doc_dict.get("text", "")
        self.metadata = doc_dict.get("metadata", {})
        self.processing_time = doc_dict.get("processing_time", 0.0)
        self.processors_used = doc_dict.get("processors_used", [])
        
        # Преобразуем sentences в объекты-обертки
        self.sentences = [UnifiedSentenceWrapper(s) for s in doc_dict.get("sentences", [])]
        
        # Преобразуем entities в объекты-обертки
        self.entities = [UnifiedEntityWrapper(e) for e in doc_dict.get("entities", [])]


class UnifiedSentenceWrapper:
    """Обертка для UnifiedSentence"""
    
    def __init__(self, sent_dict: Dict[str, Any]):
        self.idx = sent_dict.get("idx", 0)
        self.text = sent_dict.get("text", "")
        self.start_char = sent_dict.get("start_char", 0)
        self.end_char = sent_dict.get("end_char", 0)
        self.confidence = sent_dict.get("confidence", 0.0)
        self.metadata = sent_dict.get("metadata", {})
        
        # Преобразуем tokens в объекты-обертки
        self.tokens = [UnifiedTokenWrapper(t) for t in sent_dict.get("tokens", [])]
        
        # Преобразуем dependencies в объекты-обертки
        self.dependencies = [UnifiedDependencyWrapper(d) for d in sent_dict.get("dependencies", [])]
        
        # Преобразуем phrases в объекты-обертки
        self.phrases = [UnifiedPhraseWrapper(p) for p in sent_dict.get("phrases", [])]
        
        # Преобразуем entities в объекты-обертки
        self.entities = [UnifiedEntityWrapper(e) for e in sent_dict.get("entities", [])]


class UnifiedTokenWrapper:
    """Обертка для UnifiedToken"""
    
    def __init__(self, token_dict: Dict[str, Any]):
        self.idx = token_dict.get("idx", 0)
        self.text = token_dict.get("text", "")
        self.start_char = token_dict.get("start_char", 0)
        self.end_char = token_dict.get("end_char", 0)
        self.lemma = token_dict.get("lemma", "")
        self.pos = token_dict.get("pos", "")
        self.pos_fine = token_dict.get("pos_fine", "")
        self.morph = token_dict.get("morph", {})
        self.confidence = token_dict.get("confidence", 0.0)
        self.sources = token_dict.get("sources", [])
        self.is_stop = token_dict.get("is_stop", False)
        self.is_punct = token_dict.get("is_punct", False)
        self.is_space = token_dict.get("is_space", False)
        self.is_scientific_term = token_dict.get("is_scientific_term", False)
        self.scientific_category = token_dict.get("scientific_category", "")


class UnifiedDependencyWrapper:
    """Обертка для UnifiedDependency"""
    
    def __init__(self, dep_dict: Dict[str, Any]):
        self.head_idx = dep_dict.get("head_idx", 0)
        self.dependent_idx = dep_dict.get("dependent_idx", 0)
        self.relation = dep_dict.get("relation", "")
        self.confidence = dep_dict.get("confidence", 0.0)
        self.sources = dep_dict.get("sources", [])
        self.metadata = dep_dict.get("metadata", {})


class UnifiedPhraseWrapper:
    """Обертка для UnifiedPhrase"""
    
    def __init__(self, phrase_dict: Dict[str, Any]):
        self.phrase_type = phrase_dict.get("phrase_type", "")
        self.start_idx = phrase_dict.get("start_idx", 0)
        self.end_idx = phrase_dict.get("end_idx", 0)
        self.head_idx = phrase_dict.get("head_idx", 0)
        self.confidence = phrase_dict.get("confidence", 0.0)
        self.sources = phrase_dict.get("sources", [])
        self.tokens = [UnifiedTokenWrapper(t) for t in phrase_dict.get("tokens", [])]


class UnifiedEntityWrapper:
    """Обертка для UnifiedEntity"""
    
    def __init__(self, entity_dict: Dict[str, Any]):
        self._text = entity_dict.get("text", "")
        self.start_char = entity_dict.get("start_char", 0)
        self.end_char = entity_dict.get("end_char", 0)
        self.entity_type = entity_dict.get("entity_type", "")
        self.confidence = entity_dict.get("confidence", 0.0)
        self.sources = entity_dict.get("sources", [])
        self.is_scientific = entity_dict.get("is_scientific", False)
        self.scientific_domain = entity_dict.get("scientific_domain", "")
        self.metadata = entity_dict.get("metadata", {})
        # tokens будут установлены отдельно, если нужны
        self.tokens = []
    
    @property
    def text(self) -> str:
        """Возвращает текст сущности"""
        return self._text


class MultiLevelNLPService:
    """
    Service for multi-level NLP analysis.
    """

    def __init__(self):
        """Initialize service with gRPC client."""
        self.grpc_client = get_nlp_grpc_client()
        logger.info("MultiLevelNLPService инициализирован с gRPC клиентом")

    async def analyze_text(
        self,
        text: str,
        doc_id: Optional[str] = None,
        enable_voting: bool = True,
        max_level: int = 3
    ) -> Dict[str, Any]:
        """
        Analyze text with multi-level NLP.

        Args:
            text: Input text
            doc_id: Optional document ID
            enable_voting: Use voting between processors
            max_level: Maximum analysis level (1-3)

        Returns:
            Dictionary with analysis results
        """
        logger.info(f"Starting multi-level analysis (voting={enable_voting}, level={max_level})")

        # Analyze and get UnifiedDocument
        doc = await self.analyze_text_to_document(text, doc_id, enable_voting, max_level)

        # Convert to dict for response
        result = self._document_to_dict(doc)

        # Add summary statistics (извлекаем statistics из результата _calculate_summary)
        summary_dict = self._calculate_summary(doc)
        result['summary'] = summary_dict.get('statistics', {})

        # Add graph data for visualization
        result['graph'] = self._prepare_graph_data(doc)

        logger.info(f"Analysis complete in {doc.processing_time:.2f}s")
        
        # Добавляем обязательные поля для клиента
        result['doc_id'] = doc_id or doc.metadata.get('doc_id', '')
        result['text_length'] = len(doc.text)
        result['processing_time'] = doc.processing_time
        result['processed_levels'] = self._get_processed_levels(doc)

        return result
    
    def _get_processed_levels(self, doc: UnifiedDocumentWrapper) -> List[str]:
        """Определяет обработанные уровни на основе данных документа"""
        levels = []
        if not doc.sentences:
            return levels
        
        sent = doc.sentences[0]
        
        # Tokenization level - есть токены
        if sent.tokens:
            levels.append("tokenization")
        
        # Morphology level - есть POS теги
        if sent.tokens and any(t.pos for t in sent.tokens):
            levels.append("morphology")
        
        # Syntax level - есть зависимости
        if sent.dependencies:
            levels.append("syntax")
        
        return levels

    async def analyze_text_to_document(
        self,
        text: str,
        doc_id: Optional[str] = None,
        enable_voting: bool = True,
        max_level: int = 3
    ) -> UnifiedDocumentWrapper:
        """
        Analyze text and return UnifiedDocumentWrapper object (with filtering applied).

        Args:
            text: Input text
            doc_id: Optional document ID
            enable_voting: Use voting between processors
            max_level: Maximum analysis level (1-3)

        Returns:
            UnifiedDocumentWrapper with analyzed data
        """
        # Определяем уровни анализа на основе max_level
        levels = []
        if max_level >= 1:
            levels.append("tokenization")
        if max_level >= 2:
            levels.append("morphology")
        if max_level >= 3:
            levels.append("syntax")

        # Вызываем асинхронный gRPC метод (фильтрация front-matter и References на стороне NLP сервиса)
        await self.grpc_client.connect()
        grpc_result = await self.grpc_client.analyze_text(
            text=text,
            levels=levels if levels else None,
            enable_voting=enable_voting,
            min_agreement=2,
            timeout=120,
            doc_id=doc_id or "",
        )

        if not grpc_result.get("success", False):
            error_msg = grpc_result.get("message", "Unknown error")
            logger.error(f"gRPC ошибка анализа текста: {error_msg}")
            raise Exception(f"NLP service error: {error_msg}")

        # Получаем документ из gRPC ответа
        doc_dict = grpc_result.get("document")
        if not doc_dict:
            raise Exception("No document in gRPC response")

        # Добавляем doc_id в metadata
        if doc_id:
            doc_dict["metadata"]["doc_id"] = doc_id

        # Создаем обертку
        doc = UnifiedDocumentWrapper(doc_dict)

        # Store original text
        doc.metadata['original_text'] = text

        return doc

    def _remap_offsets_to_original(
        self,
        doc: UnifiedDocumentWrapper,
        offset_map: List[int]
    ) -> UnifiedDocumentWrapper:
        """
        Remap token offsets from filtered text back to original text.

        Args:
            doc: UnifiedDocument with offsets in filtered text
            offset_map: Mapping from filtered to original offsets

        Returns:
            UnifiedDocument with remapped offsets
        """
        if not offset_map:
            return doc

        for sent in doc.sentences:
            for token in sent.tokens:
                # Remap token start offset
                if token.start_char < len(offset_map):
                    token.start_char = offset_map[token.start_char]
                elif offset_map:
                    # Beyond map, extrapolate
                    token.start_char = offset_map[-1] + (token.start_char - len(offset_map) + 1)

                # Remap token end offset (end_char points to position AFTER last character)
                # So we need to remap (end_char - 1) and then add 1
                end_pos_in_filtered = token.end_char - 1
                if end_pos_in_filtered < len(offset_map):
                    # Get the position of the last character in original text
                    last_char_pos = offset_map[end_pos_in_filtered]
                    token.end_char = last_char_pos + 1
                elif offset_map:
                    # Beyond map, extrapolate
                    token.end_char = offset_map[-1] + (token.end_char - len(offset_map) + 1)

            # Remap sentence offsets
            if sent.start_char < len(offset_map):
                sent.start_char = offset_map[sent.start_char]
            elif offset_map:
                sent.start_char = offset_map[-1] + (sent.start_char - len(offset_map) + 1)

            # Same logic for sentence end
            end_pos_in_filtered = sent.end_char - 1
            if end_pos_in_filtered < len(offset_map):
                last_char_pos = offset_map[end_pos_in_filtered]
                sent.end_char = last_char_pos + 1
            elif offset_map:
                sent.end_char = offset_map[-1] + (sent.end_char - len(offset_map) + 1)

        return doc

    def _prepare_graph_data(self, doc: UnifiedDocumentWrapper) -> Dict[str, Any]:
        """
        Prepare graph data for Pixi.js visualization.

        Args:
            doc: Unified document

        Returns:
            Graph data with nodes and edges
        """
        nodes = []
        edges = []

        node_id = 0
        token_to_node = {}  # Map token idx to node id

        for sent in doc.sentences:
            # Create nodes for tokens
            for token in sent.tokens:
                # Only include content words for cleaner graph
                if not token.is_stop and not token.is_punct:
                    node = {
                        'id': node_id,
                        'label': token.text,
                        'type': 'token',
                        'pos': token.pos,
                        'lemma': token.lemma,
                        'confidence': token.confidence,
                        'sources': token.sources,
                        'sentence_idx': sent.idx,
                    }
                    nodes.append(node)
                    token_to_node[(sent.idx, token.idx)] = node_id
                    node_id += 1

            # Create edges for dependencies
            for dep in sent.dependencies:
                head_key = (sent.idx, dep.head_idx)
                dep_key = (sent.idx, dep.dependent_idx)

                if head_key in token_to_node and dep_key in token_to_node:
                    edge = {
                        'source': token_to_node[dep_key],
                        'target': token_to_node[head_key],
                        'relation': dep.relation,
                        'confidence': dep.confidence,
                        'sources': dep.sources,
                    }
                    edges.append(edge)

            # Add entity nodes
            for entity in sent.entities:
                if entity.confidence >= 0.7:  # Only high-confidence entities
                    node = {
                        'id': node_id,
                        'label': entity.text,
                        'type': 'entity',
                        'entity_type': entity.entity_type,
                        'confidence': entity.confidence,
                        'sources': entity.sources,
                        'sentence_idx': sent.idx,
                    }
                    nodes.append(node)

                    # Link entity to its tokens
                    if entity.tokens:
                        first_token_key = (sent.idx, entity.tokens[0].idx)
                        if first_token_key in token_to_node:
                            edge = {
                                'source': node_id,
                                'target': token_to_node[first_token_key],
                                'relation': 'is_entity',
                                'confidence': entity.confidence,
                            }
                            edges.append(edge)

                    node_id += 1

        return {
            'nodes': nodes,
            'edges': edges,
            'metadata': {
                'total_nodes': len(nodes),
                'total_edges': len(edges),
                'sentences': len(doc.sentences),
            }
        }

    def create_annotations_for_database(
        self,
        doc: UnifiedDocumentWrapper,
        confidence_threshold: float = 0.8
    ) -> List[Dict[str, Any]]:
        """
        Convert UnifiedDocument to annotation format for database.

        Args:
            doc: Unified document
            confidence_threshold: Minimum confidence to include

        Returns:
            List of annotation dictionaries
        """
        annotations = []
        original_text = doc.metadata.get('original_text', '')
        skipped_count = 0

        for sent in doc.sentences:
            # POS annotations
            for token in sent.tokens:
                # Include all tokens (even punct/space) but lower threshold for relations
                # Skip only spaces, keep punctuation for dependency relations
                if token.confidence >= 0.5 and not token.is_space:
                    annotation = {
                        'text': token.text,
                        'annotation_type': token.pos,  # Use UD POS tag directly
                        'start_offset': token.start_char,
                        'end_offset': token.end_char,
                        'color': self._get_color_for_pos(token.pos),
                        'metadata': {
                            'lemma': token.lemma,
                            'pos': token.pos,
                            'pos_fine': token.pos_fine,
                            'morph': token.morph,
                            'sources': token.sources,
                            'sent_idx': sent.idx,
                            'token_idx': token.idx,
                        },
                        'confidence': token.confidence,
                        'source': 'multilevel_nlp',
                        'processor_version': ','.join(token.sources),
                    }
                    annotations.append(annotation)

            # Entity annotations
            for entity in sent.entities:
                if entity.confidence >= 0.7:  # Lower threshold for entities
                    # Calculate offsets - используем start_char и end_char из entity, если есть
                    # Иначе пытаемся получить из tokens
                    if entity.start_char > 0 and entity.end_char > 0:
                        start_offset = entity.start_char
                        end_offset = entity.end_char
                    elif entity.tokens and len(entity.tokens) > 0:
                        start_offset = entity.tokens[0].start_char
                        end_offset = entity.tokens[-1].end_char
                    else:
                        # Пропускаем entity без токенов и без координат
                        skipped_count += 1
                        continue
                    entity_text = entity.text

                    annotation = {
                        'text': entity_text,
                        'annotation_type': entity.entity_type,
                        'start_offset': start_offset,
                        'end_offset': end_offset,
                        'color': self._get_color_for_entity(entity.entity_type),
                        'metadata': {
                            'entity_type': entity.entity_type,
                            'is_scientific': entity.is_scientific,
                            'sources': entity.sources,
                        },
                        'confidence': entity.confidence,
                        'source': 'multilevel_nlp',
                        'processor_version': ','.join(entity.sources),
                    }
                    annotations.append(annotation)

        logger.info(f"Created {len(annotations)} annotations (threshold={confidence_threshold}, skipped={skipped_count})")
        return annotations

    def create_relations_for_database(
        self,
        doc: UnifiedDocumentWrapper,
        annotation_uid_map: Dict[tuple, str],
        confidence_threshold: float = 0.8
    ) -> List[Dict[str, Any]]:
        """
        Convert dependencies to annotation relations.

        Args:
            doc: Unified document
            annotation_uid_map: Mapping from (sent_idx, token_idx) to annotation UID
            confidence_threshold: Minimum confidence to include

        Returns:
            List of relation dictionaries
        """
        relations = []
        missing_annotations = 0

        for sent in doc.sentences:
            for dep in sent.dependencies:
                # Lower threshold for dependencies - accept more relations
                if dep.confidence >= 0.5:  # Lower than annotation threshold
                    # Get annotation UIDs
                    head_key = (sent.idx, dep.head_idx)
                    dependent_key = (sent.idx, dep.dependent_idx)

                    head_uid = annotation_uid_map.get(head_key)
                    dependent_uid = annotation_uid_map.get(dependent_key)

                    if head_uid and dependent_uid:
                        relation = {
                            'source_uid': dependent_uid,
                            'target_uid': head_uid,
                            'relation_type': dep.relation,
                            'confidence': dep.confidence,
                            'source': 'multilevel_nlp',
                            'metadata': {
                                'confidence': dep.confidence,
                                'sources': dep.sources,
                            }
                        }
                        relations.append(relation)
                    else:
                        missing_annotations += 1

        logger.info(f"Created {len(relations)} relations (threshold=0.5, missing_annotations={missing_annotations})")
        return relations

    def _get_color_for_pos(self, pos: str) -> str:
        """Get color for POS tag."""
        colors = {
            'NOUN': '#4CAF50',      # Green
            'VERB': '#2196F3',      # Blue
            'ADJ': '#FF9800',       # Orange
            'ADV': '#9C27B0',       # Purple
            'PROPN': '#00BCD4',     # Cyan
            'PRON': '#FFEB3B',      # Yellow
            'DET': '#795548',       # Brown
            'ADP': '#607D8B',       # Blue Grey
            'NUM': '#FFC107',       # Amber
            'CONJ': '#E91E63',      # Pink
            'AUX': '#3F51B5',       # Indigo
        }
        return colors.get(pos, '#9E9E9E')  # Grey default

    def _get_color_for_entity(self, entity_type: str) -> str:
        """Get color for entity type."""
        colors = {
            'PERSON': '#E91E63',    # Pink
            'ORG': '#3F51B5',       # Indigo
            'GPE': '#009688',       # Teal
            'LOC': '#4CAF50',       # Green
            'DATE': '#FFC107',      # Amber
            'TIME': '#FF9800',      # Orange
            'MONEY': '#8BC34A',     # Light Green
            'PERCENT': '#CDDC39',   # Lime
            # Scientific entities
            'GENE': '#8BC34A',
            'PROTEIN': '#CDDC39',
            'DISEASE': '#F44336',   # Red
            'CHEMICAL': '#9C27B0',  # Purple
        }
        return colors.get(entity_type, '#795548')  # Brown default

    def _document_to_dict(self, doc: UnifiedDocumentWrapper) -> Dict[str, Any]:
        """Преобразует UnifiedDocumentWrapper в словарь для API ответа"""
        # Определяем обработанные уровни на основе наличия данных
        processed_levels = []
        if doc.sentences and len(doc.sentences) > 0:
            sent = doc.sentences[0]
            if sent.tokens:
                processed_levels.append("tokenization")
            if sent.tokens and any(t.pos for t in sent.tokens):
                processed_levels.append("morphology")
            if sent.dependencies:
                processed_levels.append("syntax")
        
        return {
            "text": doc.text,
            "doc_id": doc.metadata.get("doc_id", ""),
            "text_length": len(doc.text),
            "sentences": [
                {
                    "idx": sent.idx,
                    "text": sent.text,
                    "start_char": sent.start_char,
                    "end_char": sent.end_char,
                    "tokens": [
                        {
                            "idx": token.idx,
                            "text": token.text,
                            "start_char": token.start_char,
                            "end_char": token.end_char,
                            "lemma": token.lemma,
                            "pos": token.pos,
                            "pos_fine": token.pos_fine,
                            "morph": token.morph,
                            "confidence": token.confidence,
                            "sources": token.sources,
                            "is_stop": token.is_stop,
                            "is_punct": token.is_punct,
                            "is_space": token.is_space,
                        }
                        for token in sent.tokens
                    ],
                    "dependencies": [
                        {
                            "head_idx": dep.head_idx,
                            "dependent_idx": dep.dependent_idx,
                            "relation": dep.relation,
                            "confidence": dep.confidence,
                            "sources": dep.sources,
                        }
                        for dep in sent.dependencies
                    ],
                    "entities": [
                        {
                            "text": ent.text,
                            "start_char": ent.start_char,
                            "end_char": ent.end_char,
                            "entity_type": ent.entity_type,
                            "confidence": ent.confidence,
                            "sources": ent.sources,
                            "is_scientific": ent.is_scientific,
                        }
                        for ent in sent.entities
                    ],
                    "confidence": sent.confidence,
                }
                for sent in doc.sentences
            ],
            "entities": [
                {
                    "text": ent.text,
                    "start_char": ent.start_char,
                    "end_char": ent.end_char,
                    "entity_type": ent.entity_type,
                    "confidence": ent.confidence,
                    "sources": ent.sources,
                    "is_scientific": ent.is_scientific,
                }
                for ent in doc.entities
            ],
            "metadata": doc.metadata,
            "processing_time": doc.processing_time,
            "processors_used": doc.processors_used,
            "processed_levels": processed_levels,
        }

    def _calculate_summary(self, doc: UnifiedDocumentWrapper) -> Dict[str, Any]:
        """Вычисляет статистику для документа"""
        total_tokens = sum(len(sent.tokens) for sent in doc.sentences)
        total_dependencies = sum(len(sent.dependencies) for sent in doc.sentences)
        total_entities = len(doc.entities)
        
        # Вычисляем среднюю уверенность
        all_confidences = []
        for sent in doc.sentences:
            all_confidences.extend([token.confidence for token in sent.tokens])
            all_confidences.extend([dep.confidence for dep in sent.dependencies])
        all_confidences.extend([ent.confidence for ent in doc.entities])
        
        avg_confidence = sum(all_confidences) / len(all_confidences) if all_confidences else 0.0
        
        # Распределение POS тегов
        pos_distribution = {}
        for sent in doc.sentences:
            for token in sent.tokens:
                pos = token.pos
                pos_distribution[pos] = pos_distribution.get(pos, 0) + 1
        
        # Распределение зависимостей
        dependency_distribution = {}
        for sent in doc.sentences:
            for dep in sent.dependencies:
                rel = dep.relation
                dependency_distribution[rel] = dependency_distribution.get(rel, 0) + 1
        
        # Вычисляем agreement_score (упрощенная версия - средняя уверенность)
        agreement_score = avg_confidence
        
        return {
            "statistics": {
                "total_sentences": len(doc.sentences),
                "total_tokens": total_tokens,
                "total_dependencies": total_dependencies,
                "total_entities": total_entities,
                "agreement_score": agreement_score,
                "pos_distribution": pos_distribution,
                "dependency_distribution": dependency_distribution,
                "average_confidence": avg_confidence,
                "processing_time": doc.processing_time,
            }
        }

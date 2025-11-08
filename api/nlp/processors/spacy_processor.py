"""
spaCy processor for automatic text annotation.

This processor uses spaCy to extract:
- POS tags (18 types)
- Dependency relations (44 types)
- Named entities (18 types)
- Morphological features (14 categories)
Total: 94 annotation types
"""

import time
from typing import List, Dict, Optional, Any
import spacy
from spacy.tokens import Doc, Token

from ..base import (
    BaseNLPProcessor,
    ProcessingResult,
    AnnotationSuggestion,
    RelationSuggestion,
    AnnotationSource,
    AnnotationCategory
)
from ..mappers.spacy_mapper import SpacyMapper


class SpacyProcessor(BaseNLPProcessor):
    """
    spaCy-based NLP processor.

    Extracts linguistic annotations using spaCy's NLP pipeline.
    """

    def __init__(self, model_name: str = "en_core_web_trf"):
        """
        Initialize spaCy processor.

        Args:
            model_name: spaCy model to use (default: en_core_web_trf)
        """
        self._model_name = model_name
        self._nlp = None
        self._load_model()

    def _load_model(self):
        """Load spaCy model with fallback options."""
        try:
            self._nlp = spacy.load(self._model_name)
            print(f"Loaded spaCy model: {self._model_name}")
        except OSError:
            # Try fallback models
            fallback_models = ["en_core_web_lg", "en_core_web_md", "en_core_web_sm"]
            for fallback in fallback_models:
                try:
                    self._nlp = spacy.load(fallback)
                    self._model_name = fallback
                    print(f"Loaded fallback spaCy model: {fallback}")
                    break
                except OSError:
                    continue

            if self._nlp is None:
                raise RuntimeError(
                    "No spaCy model found. Please install one:\n"
                    "python -m spacy download en_core_web_sm"
                )

    @property
    def name(self) -> str:
        """Get processor name."""
        return "spacy"

    @property
    def version(self) -> str:
        """Get processor version."""
        return f"spacy-{spacy.__version__}_{self._model_name}"

    def process_text(
        self,
        text: str,
        annotation_types: Optional[List[str]] = None,
        min_confidence: float = 0.0
    ) -> ProcessingResult:
        """
        Process full text and extract all annotations.

        Args:
            text: Text to process
            annotation_types: Filter to specific types (None = all)
            min_confidence: Minimum confidence threshold

        Returns:
            ProcessingResult with annotations and relations
        """
        start_time = time.time()

        # Process with spaCy
        doc = self._nlp(text)

        # Extract annotations
        annotations = []
        relations = []

        # Extract POS tags
        if self._should_include_category(annotation_types, AnnotationCategory.PART_OF_SPEECH):
            annotations.extend(self._extract_pos_tags(doc))

        # Extract dependency relations and create syntax relations
        if self._should_include_category(annotation_types, AnnotationCategory.SYNTAX):
            dep_annotations, dep_relations = self._extract_dependencies(doc)
            annotations.extend(dep_annotations)
            relations.extend(dep_relations)

        # Extract named entities
        if self._should_include_category(annotation_types, AnnotationCategory.NAMED_ENTITY):
            annotations.extend(self._extract_entities(doc))

        # Extract morphological features
        if self._should_include_category(annotation_types, AnnotationCategory.MORPHOLOGY):
            annotations.extend(self._extract_morphology(doc))

        # Filter by confidence
        annotations = [ann for ann in annotations if ann.confidence >= min_confidence]
        relations = [rel for rel in relations if rel.confidence >= min_confidence]

        # Filter by specific types if requested
        if annotation_types:
            annotations = [ann for ann in annotations if ann.annotation_type in annotation_types]

        processing_time = time.time() - start_time

        return ProcessingResult(
            annotations=annotations,
            relations=relations,
            processor_name=self.name,
            processor_version=self.version,
            processing_time=processing_time,
            metadata={
                "num_tokens": len(doc),
                "num_sentences": len(list(doc.sents)),
                "model": self._model_name
            }
        )

    def process_selection(
        self,
        text: str,
        start: int,
        end: int,
        annotation_types: Optional[List[str]] = None
    ) -> ProcessingResult:
        """
        Process selected text fragment and suggest annotations.

        Args:
            text: Full text
            start: Start offset of selection
            end: End offset of selection
            annotation_types: Filter to specific types

        Returns:
            ProcessingResult with annotation suggestions for selection
        """
        start_time = time.time()

        # Process full text
        doc = self._nlp(text)

        # Find tokens in selection
        selected_tokens = []
        for token in doc:
            if token.idx >= start and token.idx < end:
                selected_tokens.append(token)

        if not selected_tokens:
            return ProcessingResult(
                annotations=[],
                relations=[],
                processor_name=self.name,
                processor_version=self.version,
                processing_time=time.time() - start_time,
                metadata={}
            )

        # Extract annotations for selected tokens
        annotations = []

        # POS tag
        if selected_tokens:
            token = selected_tokens[0]
            name, color, category = SpacyMapper.map_pos_tag(token.pos_)
            annotations.append(AnnotationSuggestion(
                text=text[start:end],
                annotation_type=name,
                category=category,
                start_offset=start,
                end_offset=end,
                confidence=0.9,
                source=AnnotationSource.SPACY,
                color=color,
                metadata={"pos_tag": token.pos_, "tag": token.tag_}
            ))

        # Dependency role
        if selected_tokens:
            token = selected_tokens[0]
            name, color, category = SpacyMapper.map_dependency(token.dep_)
            annotations.append(AnnotationSuggestion(
                text=text[start:end],
                annotation_type=name,
                category=category,
                start_offset=start,
                end_offset=end,
                confidence=0.85,
                source=AnnotationSource.SPACY,
                color=color,
                metadata={"dep": token.dep_, "head_text": token.head.text}
            ))

        # Named entity (if part of entity)
        for token in selected_tokens:
            if token.ent_type_:
                name, color, category = SpacyMapper.map_entity_type(token.ent_type_)
                annotations.append(AnnotationSuggestion(
                    text=text[start:end],
                    annotation_type=name,
                    category=category,
                    start_offset=start,
                    end_offset=end,
                    confidence=0.95,
                    source=AnnotationSource.SPACY,
                    color=color,
                    metadata={"ent_type": token.ent_type_}
                ))
                break

        # Filter by types if specified
        if annotation_types:
            annotations = [ann for ann in annotations if ann.annotation_type in annotation_types]

        processing_time = time.time() - start_time

        return ProcessingResult(
            annotations=annotations,
            relations=[],
            processor_name=self.name,
            processor_version=self.version,
            processing_time=processing_time,
            metadata={"num_selected_tokens": len(selected_tokens)}
        )

    def get_supported_types(self) -> Dict[AnnotationCategory, List[str]]:
        """
        Get all annotation types supported by spaCy.

        Returns:
            Dictionary mapping categories to lists of types (Russian names)
        """
        all_types = SpacyMapper.get_all_types()

        return {
            category: [name for name, _ in types.values()]
            for category, types in all_types.items()
        }

    def _extract_pos_tags(self, doc: Doc) -> List[AnnotationSuggestion]:
        """Extract POS tag annotations."""
        annotations = []

        for token in doc:
            # Skip punctuation and whitespace
            if token.is_punct or token.is_space:
                continue

            name, color, category = SpacyMapper.map_pos_tag(token.pos_)

            annotations.append(AnnotationSuggestion(
                text=token.text,
                annotation_type=name,
                category=category,
                start_offset=token.idx,
                end_offset=token.idx + len(token.text),
                confidence=0.9,
                source=AnnotationSource.SPACY,
                color=color,
                metadata={
                    "pos_tag": token.pos_,
                    "tag": token.tag_,
                    "lemma": token.lemma_
                }
            ))

        return annotations

    def _extract_dependencies(
        self,
        doc: Doc
    ) -> tuple[List[AnnotationSuggestion], List[RelationSuggestion]]:
        """Extract dependency annotations and relations."""
        annotations = []
        relations = []

        for token in doc:
            # Skip ROOT and punctuation
            if token.dep_ == "ROOT" or token.is_punct:
                continue

            name, color, category = SpacyMapper.map_dependency(token.dep_)

            # Create annotation for the dependent token
            annotations.append(AnnotationSuggestion(
                text=token.text,
                annotation_type=name,
                category=category,
                start_offset=token.idx,
                end_offset=token.idx + len(token.text),
                confidence=0.85,
                source=AnnotationSource.SPACY,
                color=color,
                metadata={
                    "dep": token.dep_,
                    "head_text": token.head.text,
                    "head_pos": token.head.pos_
                }
            ))

            # Create relation from dependent to head
            relations.append(RelationSuggestion(
                source_text=token.text,
                target_text=token.head.text,
                source_start=token.idx,
                source_end=token.idx + len(token.text),
                target_start=token.head.idx,
                target_end=token.head.idx + len(token.head.text),
                relation_type=name,
                confidence=0.85,
                source=AnnotationSource.SPACY,
                metadata={
                    "dep": token.dep_,
                    "distance": abs(token.i - token.head.i)
                }
            ))

        return annotations, relations

    def _extract_entities(self, doc: Doc) -> List[AnnotationSuggestion]:
        """Extract named entity annotations."""
        annotations = []

        for ent in doc.ents:
            name, color, category = SpacyMapper.map_entity_type(ent.label_)

            annotations.append(AnnotationSuggestion(
                text=ent.text,
                annotation_type=name,
                category=category,
                start_offset=ent.start_char,
                end_offset=ent.end_char,
                confidence=0.95,
                source=AnnotationSource.SPACY,
                color=color,
                metadata={
                    "ent_type": ent.label_,
                    "ent_id": ent.ent_id_
                }
            ))

        return annotations

    def _extract_morphology(self, doc: Doc) -> List[AnnotationSuggestion]:
        """Extract morphological feature annotations."""
        annotations = []

        for token in doc:
            # Skip tokens without morphology
            if not token.morph:
                continue

            # Extract all morphological features
            morph_dict = token.morph.to_dict()

            for feature, value in morph_dict.items():
                name, color, category = SpacyMapper.map_morph_feature(feature)

                # Create annotation with feature name and value
                full_name = f"{name}: {value}"

                annotations.append(AnnotationSuggestion(
                    text=token.text,
                    annotation_type=full_name,
                    category=category,
                    start_offset=token.idx,
                    end_offset=token.idx + len(token.text),
                    confidence=0.8,
                    source=AnnotationSource.SPACY,
                    color=color,
                    metadata={
                        "morph_feature": feature,
                        "morph_value": value,
                        "all_morph": morph_dict
                    }
                ))

        return annotations

    def _should_include_category(
        self,
        annotation_types: Optional[List[str]],
        category: AnnotationCategory
    ) -> bool:
        """Check if category should be included based on filter."""
        if annotation_types is None:
            return True

        # Get all types in this category
        supported = self.get_supported_types()
        category_types = supported.get(category, [])

        # Check if any requested type is in this category
        return any(t in annotation_types for t in category_types)

"""
NLP Manager for coordinating multiple NLP processors.

This module manages registration and coordination of multiple NLP processors,
allowing them to work together and combine their results.
"""

import time
from typing import List, Dict, Optional, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

from .base import (
    BaseNLPProcessor,
    ProcessingResult,
    AnnotationSuggestion,
    RelationSuggestion,
    AnnotationCategory
)


class NLPManager:
    """
    Manager for coordinating multiple NLP processors.

    Allows registering multiple processors and running them in parallel
    to generate comprehensive annotations.
    """

    def __init__(self):
        """Initialize NLP manager."""
        self._processors: Dict[str, BaseNLPProcessor] = {}

    def register_processor(self, processor: BaseNLPProcessor) -> None:
        """
        Register an NLP processor.

        Args:
            processor: Processor to register

        Raises:
            ValueError: If processor with same name already registered
        """
        if processor.name in self._processors:
            raise ValueError(f"Processor '{processor.name}' is already registered")

        self._processors[processor.name] = processor

    def unregister_processor(self, processor_name: str) -> None:
        """
        Unregister an NLP processor.

        Args:
            processor_name: Name of processor to unregister
        """
        self._processors.pop(processor_name, None)

    def get_processor(self, processor_name: str) -> Optional[BaseNLPProcessor]:
        """
        Get registered processor by name.

        Args:
            processor_name: Name of processor

        Returns:
            Processor instance or None if not found
        """
        return self._processors.get(processor_name)

    def list_processors(self) -> List[str]:
        """
        Get list of registered processor names.

        Returns:
            List of processor names
        """
        return list(self._processors.keys())

    def process_text(
        self,
        text: str,
        processor_names: Optional[List[str]] = None,
        annotation_types: Optional[List[str]] = None,
        min_confidence: float = 0.0,
        parallel: bool = True
    ) -> Dict[str, ProcessingResult]:
        """
        Process text with one or more processors.

        Args:
            text: Text to process
            processor_names: Names of processors to use (None = all)
            annotation_types: Filter to specific types (None = all)
            min_confidence: Minimum confidence threshold
            parallel: Run processors in parallel if True

        Returns:
            Dictionary mapping processor names to their results
        """
        # Determine which processors to use
        processors_to_use = self._get_processors_to_use(processor_names)

        if not processors_to_use:
            return {}

        # Process with each processor
        if parallel and len(processors_to_use) > 1:
            return self._process_parallel(
                processors_to_use,
                text,
                annotation_types,
                min_confidence
            )
        else:
            return self._process_sequential(
                processors_to_use,
                text,
                annotation_types,
                min_confidence
            )

    def process_selection(
        self,
        text: str,
        start: int,
        end: int,
        processor_names: Optional[List[str]] = None,
        annotation_types: Optional[List[str]] = None
    ) -> Dict[str, ProcessingResult]:
        """
        Process selected text fragment with one or more processors.

        Args:
            text: Full text
            start: Start offset of selection
            end: End offset of selection
            processor_names: Names of processors to use (None = all)
            annotation_types: Filter to specific types (None = all)

        Returns:
            Dictionary mapping processor names to their results
        """
        processors_to_use = self._get_processors_to_use(processor_names)

        if not processors_to_use:
            return {}

        results = {}
        for name, processor in processors_to_use.items():
            try:
                result = processor.process_selection(
                    text,
                    start,
                    end,
                    annotation_types
                )
                results[name] = result
            except Exception as e:
                print(f"Error processing with {name}: {e}")
                # Continue with other processors

        return results

    def get_all_supported_types(self) -> Dict[AnnotationCategory, List[str]]:
        """
        Get all annotation types supported by all registered processors.

        Returns:
            Dictionary mapping categories to lists of annotation types
        """
        all_types: Dict[AnnotationCategory, set] = {}

        for processor in self._processors.values():
            processor_types = processor.get_supported_types()
            for category, types in processor_types.items():
                if category not in all_types:
                    all_types[category] = set()
                all_types[category].update(types)

        # Convert sets to sorted lists
        return {
            category: sorted(list(types))
            for category, types in all_types.items()
        }

    def merge_results(
        self,
        results: Dict[str, ProcessingResult],
        dedup_annotations: bool = True,
        dedup_relations: bool = True
    ) -> ProcessingResult:
        """
        Merge results from multiple processors into single result.

        Args:
            results: Dictionary of results from different processors
            dedup_annotations: Remove duplicate annotations
            dedup_relations: Remove duplicate relations

        Returns:
            Merged ProcessingResult
        """
        all_annotations: List[AnnotationSuggestion] = []
        all_relations: List[RelationSuggestion] = []
        total_time = 0.0
        processors_used = []

        for proc_name, result in results.items():
            all_annotations.extend(result.annotations)
            all_relations.extend(result.relations)
            total_time += result.processing_time
            processors_used.append(f"{result.processor_name} v{result.processor_version}")

        # Deduplicate if requested
        if dedup_annotations:
            all_annotations = self._deduplicate_annotations(all_annotations)

        if dedup_relations:
            all_relations = self._deduplicate_relations(all_relations)

        return ProcessingResult(
            annotations=all_annotations,
            relations=all_relations,
            processor_name="merged",
            processor_version=", ".join(processors_used),
            processing_time=total_time,
            metadata={
                "processors_used": processors_used,
                "num_processors": len(results)
            }
        )

    def _get_processors_to_use(
        self,
        processor_names: Optional[List[str]]
    ) -> Dict[str, BaseNLPProcessor]:
        """Get processors to use based on names."""
        if processor_names is None:
            # Use all registered processors
            return self._processors.copy()

        # Use only specified processors
        processors = {}
        for name in processor_names:
            processor = self._processors.get(name)
            if processor:
                processors[name] = processor
            else:
                print(f"Warning: Processor '{name}' not found")

        return processors

    def _process_sequential(
        self,
        processors: Dict[str, BaseNLPProcessor],
        text: str,
        annotation_types: Optional[List[str]],
        min_confidence: float
    ) -> Dict[str, ProcessingResult]:
        """Process text sequentially with each processor."""
        results = {}

        for name, processor in processors.items():
            try:
                result = processor.process_text(
                    text,
                    annotation_types,
                    min_confidence
                )
                results[name] = result
            except Exception as e:
                print(f"Error processing with {name}: {e}")
                # Continue with other processors

        return results

    def _process_parallel(
        self,
        processors: Dict[str, BaseNLPProcessor],
        text: str,
        annotation_types: Optional[List[str]],
        min_confidence: float
    ) -> Dict[str, ProcessingResult]:
        """Process text in parallel with multiple processors."""
        results = {}

        with ThreadPoolExecutor(max_workers=len(processors)) as executor:
            # Submit all tasks
            future_to_name = {
                executor.submit(
                    processor.process_text,
                    text,
                    annotation_types,
                    min_confidence
                ): name
                for name, processor in processors.items()
            }

            # Collect results as they complete
            for future in as_completed(future_to_name):
                name = future_to_name[future]
                try:
                    result = future.result()
                    results[name] = result
                except Exception as e:
                    print(f"Error processing with {name}: {e}")
                    # Continue with other processors

        return results

    def _deduplicate_annotations(
        self,
        annotations: List[AnnotationSuggestion]
    ) -> List[AnnotationSuggestion]:
        """
        Remove duplicate annotations based on text span and type.

        If multiple annotations have same span and type, keep the one with highest confidence.
        """
        # Group by (start, end, type)
        groups: Dict[tuple, List[AnnotationSuggestion]] = {}

        for ann in annotations:
            key = (ann.start_offset, ann.end_offset, ann.annotation_type)
            if key not in groups:
                groups[key] = []
            groups[key].append(ann)

        # Keep best from each group
        deduplicated = []
        for group in groups.values():
            # Sort by confidence descending
            group.sort(key=lambda x: x.confidence, reverse=True)
            deduplicated.append(group[0])

        return deduplicated

    def _deduplicate_relations(
        self,
        relations: List[RelationSuggestion]
    ) -> List[RelationSuggestion]:
        """
        Remove duplicate relations based on source/target spans and type.

        If multiple relations have same spans and type, keep the one with highest confidence.
        """
        # Group by (source_start, source_end, target_start, target_end, relation_type)
        groups: Dict[tuple, List[RelationSuggestion]] = {}

        for rel in relations:
            key = (
                rel.source_start,
                rel.source_end,
                rel.target_start,
                rel.target_end,
                rel.relation_type
            )
            if key not in groups:
                groups[key] = []
            groups[key].append(rel)

        # Keep best from each group
        deduplicated = []
        for group in groups.values():
            # Sort by confidence descending
            group.sort(key=lambda x: x.confidence, reverse=True)
            deduplicated.append(group[0])

        return deduplicated

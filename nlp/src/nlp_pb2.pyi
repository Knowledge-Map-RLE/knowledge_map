from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class AnnotationSource(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    ANNOTATION_SOURCE_UNSPECIFIED: _ClassVar[AnnotationSource]
    USER: _ClassVar[AnnotationSource]
    SPACY: _ClassVar[AnnotationSource]
    CUSTOM: _ClassVar[AnnotationSource]
    FILE: _ClassVar[AnnotationSource]
    NLTK: _ClassVar[AnnotationSource]
    STANZA: _ClassVar[AnnotationSource]
    UDPIPE: _ClassVar[AnnotationSource]

class AnnotationCategory(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    ANNOTATION_CATEGORY_UNSPECIFIED: _ClassVar[AnnotationCategory]
    ANNOTATION_PART_OF_SPEECH: _ClassVar[AnnotationCategory]
    ANNOTATION_SYNTAX: _ClassVar[AnnotationCategory]
    ANNOTATION_NAMED_ENTITY: _ClassVar[AnnotationCategory]
    ANNOTATION_MORPHOLOGY: _ClassVar[AnnotationCategory]
    ANNOTATION_SENTENCE_MEMBER: _ClassVar[AnnotationCategory]
    ANNOTATION_SCIENTIFIC_ENTITY: _ClassVar[AnnotationCategory]
    ANNOTATION_GENERAL_ENTITY: _ClassVar[AnnotationCategory]

class LinguisticLevel(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    LINGUISTIC_LEVEL_UNSPECIFIED: _ClassVar[LinguisticLevel]
    LEVEL_TOKENIZATION: _ClassVar[LinguisticLevel]
    LEVEL_MORPHOLOGY: _ClassVar[LinguisticLevel]
    LEVEL_SYNTAX: _ClassVar[LinguisticLevel]
    LEVEL_SEMANTIC_ROLES: _ClassVar[LinguisticLevel]
    LEVEL_LEXICAL_SEMANTICS: _ClassVar[LinguisticLevel]
    LEVEL_DISCOURSE: _ClassVar[LinguisticLevel]

class ValidationErrorSeverity(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    VALIDATION_ERROR_SEVERITY_UNSPECIFIED: _ClassVar[ValidationErrorSeverity]
    VALIDATION_ERROR_SEVERITY_ERROR: _ClassVar[ValidationErrorSeverity]
    VALIDATION_ERROR_SEVERITY_WARNING: _ClassVar[ValidationErrorSeverity]
    VALIDATION_ERROR_SEVERITY_INFO: _ClassVar[ValidationErrorSeverity]
ANNOTATION_SOURCE_UNSPECIFIED: AnnotationSource
USER: AnnotationSource
SPACY: AnnotationSource
CUSTOM: AnnotationSource
FILE: AnnotationSource
NLTK: AnnotationSource
STANZA: AnnotationSource
UDPIPE: AnnotationSource
ANNOTATION_CATEGORY_UNSPECIFIED: AnnotationCategory
ANNOTATION_PART_OF_SPEECH: AnnotationCategory
ANNOTATION_SYNTAX: AnnotationCategory
ANNOTATION_NAMED_ENTITY: AnnotationCategory
ANNOTATION_MORPHOLOGY: AnnotationCategory
ANNOTATION_SENTENCE_MEMBER: AnnotationCategory
ANNOTATION_SCIENTIFIC_ENTITY: AnnotationCategory
ANNOTATION_GENERAL_ENTITY: AnnotationCategory
LINGUISTIC_LEVEL_UNSPECIFIED: LinguisticLevel
LEVEL_TOKENIZATION: LinguisticLevel
LEVEL_MORPHOLOGY: LinguisticLevel
LEVEL_SYNTAX: LinguisticLevel
LEVEL_SEMANTIC_ROLES: LinguisticLevel
LEVEL_LEXICAL_SEMANTICS: LinguisticLevel
LEVEL_DISCOURSE: LinguisticLevel
VALIDATION_ERROR_SEVERITY_UNSPECIFIED: ValidationErrorSeverity
VALIDATION_ERROR_SEVERITY_ERROR: ValidationErrorSeverity
VALIDATION_ERROR_SEVERITY_WARNING: ValidationErrorSeverity
VALIDATION_ERROR_SEVERITY_INFO: ValidationErrorSeverity

class AnnotationSuggestion(_message.Message):
    __slots__ = ("text", "annotation_type", "category", "start_offset", "end_offset", "confidence", "source", "color", "metadata")
    class MetadataEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    TEXT_FIELD_NUMBER: _ClassVar[int]
    ANNOTATION_TYPE_FIELD_NUMBER: _ClassVar[int]
    CATEGORY_FIELD_NUMBER: _ClassVar[int]
    START_OFFSET_FIELD_NUMBER: _ClassVar[int]
    END_OFFSET_FIELD_NUMBER: _ClassVar[int]
    CONFIDENCE_FIELD_NUMBER: _ClassVar[int]
    SOURCE_FIELD_NUMBER: _ClassVar[int]
    COLOR_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    text: str
    annotation_type: str
    category: AnnotationCategory
    start_offset: int
    end_offset: int
    confidence: float
    source: AnnotationSource
    color: str
    metadata: _containers.ScalarMap[str, str]
    def __init__(self, text: _Optional[str] = ..., annotation_type: _Optional[str] = ..., category: _Optional[_Union[AnnotationCategory, str]] = ..., start_offset: _Optional[int] = ..., end_offset: _Optional[int] = ..., confidence: _Optional[float] = ..., source: _Optional[_Union[AnnotationSource, str]] = ..., color: _Optional[str] = ..., metadata: _Optional[_Mapping[str, str]] = ...) -> None: ...

class RelationSuggestion(_message.Message):
    __slots__ = ("source_text", "target_text", "source_start", "source_end", "target_start", "target_end", "relation_type", "confidence", "source", "metadata")
    class MetadataEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    SOURCE_TEXT_FIELD_NUMBER: _ClassVar[int]
    TARGET_TEXT_FIELD_NUMBER: _ClassVar[int]
    SOURCE_START_FIELD_NUMBER: _ClassVar[int]
    SOURCE_END_FIELD_NUMBER: _ClassVar[int]
    TARGET_START_FIELD_NUMBER: _ClassVar[int]
    TARGET_END_FIELD_NUMBER: _ClassVar[int]
    RELATION_TYPE_FIELD_NUMBER: _ClassVar[int]
    CONFIDENCE_FIELD_NUMBER: _ClassVar[int]
    SOURCE_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    source_text: str
    target_text: str
    source_start: int
    source_end: int
    target_start: int
    target_end: int
    relation_type: str
    confidence: float
    source: AnnotationSource
    metadata: _containers.ScalarMap[str, str]
    def __init__(self, source_text: _Optional[str] = ..., target_text: _Optional[str] = ..., source_start: _Optional[int] = ..., source_end: _Optional[int] = ..., target_start: _Optional[int] = ..., target_end: _Optional[int] = ..., relation_type: _Optional[str] = ..., confidence: _Optional[float] = ..., source: _Optional[_Union[AnnotationSource, str]] = ..., metadata: _Optional[_Mapping[str, str]] = ...) -> None: ...

class ProcessingResult(_message.Message):
    __slots__ = ("annotations", "relations", "processor_name", "processor_version", "processing_time", "metadata")
    class MetadataEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    ANNOTATIONS_FIELD_NUMBER: _ClassVar[int]
    RELATIONS_FIELD_NUMBER: _ClassVar[int]
    PROCESSOR_NAME_FIELD_NUMBER: _ClassVar[int]
    PROCESSOR_VERSION_FIELD_NUMBER: _ClassVar[int]
    PROCESSING_TIME_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    annotations: _containers.RepeatedCompositeFieldContainer[AnnotationSuggestion]
    relations: _containers.RepeatedCompositeFieldContainer[RelationSuggestion]
    processor_name: str
    processor_version: str
    processing_time: float
    metadata: _containers.ScalarMap[str, str]
    def __init__(self, annotations: _Optional[_Iterable[_Union[AnnotationSuggestion, _Mapping]]] = ..., relations: _Optional[_Iterable[_Union[RelationSuggestion, _Mapping]]] = ..., processor_name: _Optional[str] = ..., processor_version: _Optional[str] = ..., processing_time: _Optional[float] = ..., metadata: _Optional[_Mapping[str, str]] = ...) -> None: ...

class UnifiedToken(_message.Message):
    __slots__ = ("idx", "text", "start_char", "end_char", "lemma", "pos", "pos_fine", "morph", "confidence", "sources", "is_stop", "is_punct", "is_space", "is_scientific_term", "scientific_category")
    class MorphEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    IDX_FIELD_NUMBER: _ClassVar[int]
    TEXT_FIELD_NUMBER: _ClassVar[int]
    START_CHAR_FIELD_NUMBER: _ClassVar[int]
    END_CHAR_FIELD_NUMBER: _ClassVar[int]
    LEMMA_FIELD_NUMBER: _ClassVar[int]
    POS_FIELD_NUMBER: _ClassVar[int]
    POS_FINE_FIELD_NUMBER: _ClassVar[int]
    MORPH_FIELD_NUMBER: _ClassVar[int]
    CONFIDENCE_FIELD_NUMBER: _ClassVar[int]
    SOURCES_FIELD_NUMBER: _ClassVar[int]
    IS_STOP_FIELD_NUMBER: _ClassVar[int]
    IS_PUNCT_FIELD_NUMBER: _ClassVar[int]
    IS_SPACE_FIELD_NUMBER: _ClassVar[int]
    IS_SCIENTIFIC_TERM_FIELD_NUMBER: _ClassVar[int]
    SCIENTIFIC_CATEGORY_FIELD_NUMBER: _ClassVar[int]
    idx: int
    text: str
    start_char: int
    end_char: int
    lemma: str
    pos: str
    pos_fine: str
    morph: _containers.ScalarMap[str, str]
    confidence: float
    sources: _containers.RepeatedScalarFieldContainer[str]
    is_stop: bool
    is_punct: bool
    is_space: bool
    is_scientific_term: bool
    scientific_category: str
    def __init__(self, idx: _Optional[int] = ..., text: _Optional[str] = ..., start_char: _Optional[int] = ..., end_char: _Optional[int] = ..., lemma: _Optional[str] = ..., pos: _Optional[str] = ..., pos_fine: _Optional[str] = ..., morph: _Optional[_Mapping[str, str]] = ..., confidence: _Optional[float] = ..., sources: _Optional[_Iterable[str]] = ..., is_stop: bool = ..., is_punct: bool = ..., is_space: bool = ..., is_scientific_term: bool = ..., scientific_category: _Optional[str] = ...) -> None: ...

class UnifiedDependency(_message.Message):
    __slots__ = ("head_idx", "dependent_idx", "relation", "confidence", "sources", "metadata")
    class MetadataEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    HEAD_IDX_FIELD_NUMBER: _ClassVar[int]
    DEPENDENT_IDX_FIELD_NUMBER: _ClassVar[int]
    RELATION_FIELD_NUMBER: _ClassVar[int]
    CONFIDENCE_FIELD_NUMBER: _ClassVar[int]
    SOURCES_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    head_idx: int
    dependent_idx: int
    relation: str
    confidence: float
    sources: _containers.RepeatedScalarFieldContainer[str]
    metadata: _containers.ScalarMap[str, str]
    def __init__(self, head_idx: _Optional[int] = ..., dependent_idx: _Optional[int] = ..., relation: _Optional[str] = ..., confidence: _Optional[float] = ..., sources: _Optional[_Iterable[str]] = ..., metadata: _Optional[_Mapping[str, str]] = ...) -> None: ...

class UnifiedPhrase(_message.Message):
    __slots__ = ("phrase_type", "start_idx", "end_idx", "tokens", "head_idx", "confidence", "sources")
    PHRASE_TYPE_FIELD_NUMBER: _ClassVar[int]
    START_IDX_FIELD_NUMBER: _ClassVar[int]
    END_IDX_FIELD_NUMBER: _ClassVar[int]
    TOKENS_FIELD_NUMBER: _ClassVar[int]
    HEAD_IDX_FIELD_NUMBER: _ClassVar[int]
    CONFIDENCE_FIELD_NUMBER: _ClassVar[int]
    SOURCES_FIELD_NUMBER: _ClassVar[int]
    phrase_type: str
    start_idx: int
    end_idx: int
    tokens: _containers.RepeatedCompositeFieldContainer[UnifiedToken]
    head_idx: int
    confidence: float
    sources: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, phrase_type: _Optional[str] = ..., start_idx: _Optional[int] = ..., end_idx: _Optional[int] = ..., tokens: _Optional[_Iterable[_Union[UnifiedToken, _Mapping]]] = ..., head_idx: _Optional[int] = ..., confidence: _Optional[float] = ..., sources: _Optional[_Iterable[str]] = ...) -> None: ...

class UnifiedEntity(_message.Message):
    __slots__ = ("text", "start_char", "end_char", "entity_type", "confidence", "sources", "is_scientific", "scientific_domain", "metadata")
    class MetadataEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    TEXT_FIELD_NUMBER: _ClassVar[int]
    START_CHAR_FIELD_NUMBER: _ClassVar[int]
    END_CHAR_FIELD_NUMBER: _ClassVar[int]
    ENTITY_TYPE_FIELD_NUMBER: _ClassVar[int]
    CONFIDENCE_FIELD_NUMBER: _ClassVar[int]
    SOURCES_FIELD_NUMBER: _ClassVar[int]
    IS_SCIENTIFIC_FIELD_NUMBER: _ClassVar[int]
    SCIENTIFIC_DOMAIN_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    text: str
    start_char: int
    end_char: int
    entity_type: str
    confidence: float
    sources: _containers.RepeatedScalarFieldContainer[str]
    is_scientific: bool
    scientific_domain: str
    metadata: _containers.ScalarMap[str, str]
    def __init__(self, text: _Optional[str] = ..., start_char: _Optional[int] = ..., end_char: _Optional[int] = ..., entity_type: _Optional[str] = ..., confidence: _Optional[float] = ..., sources: _Optional[_Iterable[str]] = ..., is_scientific: bool = ..., scientific_domain: _Optional[str] = ..., metadata: _Optional[_Mapping[str, str]] = ...) -> None: ...

class UnifiedSentence(_message.Message):
    __slots__ = ("idx", "text", "start_char", "end_char", "tokens", "dependencies", "phrases", "entities", "confidence", "metadata")
    class MetadataEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    IDX_FIELD_NUMBER: _ClassVar[int]
    TEXT_FIELD_NUMBER: _ClassVar[int]
    START_CHAR_FIELD_NUMBER: _ClassVar[int]
    END_CHAR_FIELD_NUMBER: _ClassVar[int]
    TOKENS_FIELD_NUMBER: _ClassVar[int]
    DEPENDENCIES_FIELD_NUMBER: _ClassVar[int]
    PHRASES_FIELD_NUMBER: _ClassVar[int]
    ENTITIES_FIELD_NUMBER: _ClassVar[int]
    CONFIDENCE_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    idx: int
    text: str
    start_char: int
    end_char: int
    tokens: _containers.RepeatedCompositeFieldContainer[UnifiedToken]
    dependencies: _containers.RepeatedCompositeFieldContainer[UnifiedDependency]
    phrases: _containers.RepeatedCompositeFieldContainer[UnifiedPhrase]
    entities: _containers.RepeatedCompositeFieldContainer[UnifiedEntity]
    confidence: float
    metadata: _containers.ScalarMap[str, str]
    def __init__(self, idx: _Optional[int] = ..., text: _Optional[str] = ..., start_char: _Optional[int] = ..., end_char: _Optional[int] = ..., tokens: _Optional[_Iterable[_Union[UnifiedToken, _Mapping]]] = ..., dependencies: _Optional[_Iterable[_Union[UnifiedDependency, _Mapping]]] = ..., phrases: _Optional[_Iterable[_Union[UnifiedPhrase, _Mapping]]] = ..., entities: _Optional[_Iterable[_Union[UnifiedEntity, _Mapping]]] = ..., confidence: _Optional[float] = ..., metadata: _Optional[_Mapping[str, str]] = ...) -> None: ...

class UnifiedDocument(_message.Message):
    __slots__ = ("text", "sentences", "entities", "metadata", "processing_time", "processors_used")
    class MetadataEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    TEXT_FIELD_NUMBER: _ClassVar[int]
    SENTENCES_FIELD_NUMBER: _ClassVar[int]
    ENTITIES_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    PROCESSING_TIME_FIELD_NUMBER: _ClassVar[int]
    PROCESSORS_USED_FIELD_NUMBER: _ClassVar[int]
    text: str
    sentences: _containers.RepeatedCompositeFieldContainer[UnifiedSentence]
    entities: _containers.RepeatedCompositeFieldContainer[UnifiedEntity]
    metadata: _containers.ScalarMap[str, str]
    processing_time: float
    processors_used: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, text: _Optional[str] = ..., sentences: _Optional[_Iterable[_Union[UnifiedSentence, _Mapping]]] = ..., entities: _Optional[_Iterable[_Union[UnifiedEntity, _Mapping]]] = ..., metadata: _Optional[_Mapping[str, str]] = ..., processing_time: _Optional[float] = ..., processors_used: _Optional[_Iterable[str]] = ...) -> None: ...

class ProcessTextRequest(_message.Message):
    __slots__ = ("text", "processor_names", "merge_results")
    TEXT_FIELD_NUMBER: _ClassVar[int]
    PROCESSOR_NAMES_FIELD_NUMBER: _ClassVar[int]
    MERGE_RESULTS_FIELD_NUMBER: _ClassVar[int]
    text: str
    processor_names: _containers.RepeatedScalarFieldContainer[str]
    merge_results: bool
    def __init__(self, text: _Optional[str] = ..., processor_names: _Optional[_Iterable[str]] = ..., merge_results: bool = ...) -> None: ...

class ProcessTextResponse(_message.Message):
    __slots__ = ("success", "results", "merged_result", "message")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    RESULTS_FIELD_NUMBER: _ClassVar[int]
    MERGED_RESULT_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    success: bool
    results: _containers.RepeatedCompositeFieldContainer[ProcessingResult]
    merged_result: ProcessingResult
    message: str
    def __init__(self, success: bool = ..., results: _Optional[_Iterable[_Union[ProcessingResult, _Mapping]]] = ..., merged_result: _Optional[_Union[ProcessingResult, _Mapping]] = ..., message: _Optional[str] = ...) -> None: ...

class ProcessSelectionRequest(_message.Message):
    __slots__ = ("text", "selection", "start_offset", "end_offset", "processor_names", "merge_results")
    TEXT_FIELD_NUMBER: _ClassVar[int]
    SELECTION_FIELD_NUMBER: _ClassVar[int]
    START_OFFSET_FIELD_NUMBER: _ClassVar[int]
    END_OFFSET_FIELD_NUMBER: _ClassVar[int]
    PROCESSOR_NAMES_FIELD_NUMBER: _ClassVar[int]
    MERGE_RESULTS_FIELD_NUMBER: _ClassVar[int]
    text: str
    selection: str
    start_offset: int
    end_offset: int
    processor_names: _containers.RepeatedScalarFieldContainer[str]
    merge_results: bool
    def __init__(self, text: _Optional[str] = ..., selection: _Optional[str] = ..., start_offset: _Optional[int] = ..., end_offset: _Optional[int] = ..., processor_names: _Optional[_Iterable[str]] = ..., merge_results: bool = ...) -> None: ...

class ProcessSelectionResponse(_message.Message):
    __slots__ = ("success", "results", "merged_result", "message")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    RESULTS_FIELD_NUMBER: _ClassVar[int]
    MERGED_RESULT_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    success: bool
    results: _containers.RepeatedCompositeFieldContainer[ProcessingResult]
    merged_result: ProcessingResult
    message: str
    def __init__(self, success: bool = ..., results: _Optional[_Iterable[_Union[ProcessingResult, _Mapping]]] = ..., merged_result: _Optional[_Union[ProcessingResult, _Mapping]] = ..., message: _Optional[str] = ...) -> None: ...

class AnalyzeTextRequest(_message.Message):
    __slots__ = ("text", "levels", "enable_voting", "min_agreement")
    TEXT_FIELD_NUMBER: _ClassVar[int]
    LEVELS_FIELD_NUMBER: _ClassVar[int]
    ENABLE_VOTING_FIELD_NUMBER: _ClassVar[int]
    MIN_AGREEMENT_FIELD_NUMBER: _ClassVar[int]
    text: str
    levels: _containers.RepeatedScalarFieldContainer[LinguisticLevel]
    enable_voting: bool
    min_agreement: int
    def __init__(self, text: _Optional[str] = ..., levels: _Optional[_Iterable[_Union[LinguisticLevel, str]]] = ..., enable_voting: bool = ..., min_agreement: _Optional[int] = ...) -> None: ...

class AnalyzeTextResponse(_message.Message):
    __slots__ = ("success", "document", "message", "processing_time")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    DOCUMENT_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    PROCESSING_TIME_FIELD_NUMBER: _ClassVar[int]
    success: bool
    document: UnifiedDocument
    message: str
    processing_time: float
    def __init__(self, success: bool = ..., document: _Optional[_Union[UnifiedDocument, _Mapping]] = ..., message: _Optional[str] = ..., processing_time: _Optional[float] = ...) -> None: ...

class ProcessorInfo(_message.Message):
    __slots__ = ("name", "version", "description", "supported_categories", "supported_levels", "available")
    NAME_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    SUPPORTED_CATEGORIES_FIELD_NUMBER: _ClassVar[int]
    SUPPORTED_LEVELS_FIELD_NUMBER: _ClassVar[int]
    AVAILABLE_FIELD_NUMBER: _ClassVar[int]
    name: str
    version: str
    description: str
    supported_categories: _containers.RepeatedScalarFieldContainer[AnnotationCategory]
    supported_levels: _containers.RepeatedScalarFieldContainer[LinguisticLevel]
    available: bool
    def __init__(self, name: _Optional[str] = ..., version: _Optional[str] = ..., description: _Optional[str] = ..., supported_categories: _Optional[_Iterable[_Union[AnnotationCategory, str]]] = ..., supported_levels: _Optional[_Iterable[_Union[LinguisticLevel, str]]] = ..., available: bool = ...) -> None: ...

class GetSupportedTypesRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class GetSupportedTypesResponse(_message.Message):
    __slots__ = ("processors", "annotation_types", "relation_types")
    PROCESSORS_FIELD_NUMBER: _ClassVar[int]
    ANNOTATION_TYPES_FIELD_NUMBER: _ClassVar[int]
    RELATION_TYPES_FIELD_NUMBER: _ClassVar[int]
    processors: _containers.RepeatedCompositeFieldContainer[ProcessorInfo]
    annotation_types: _containers.RepeatedScalarFieldContainer[str]
    relation_types: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, processors: _Optional[_Iterable[_Union[ProcessorInfo, _Mapping]]] = ..., annotation_types: _Optional[_Iterable[str]] = ..., relation_types: _Optional[_Iterable[str]] = ...) -> None: ...

class ValidationErrorMessage(_message.Message):
    __slots__ = ("error_type", "message", "severity", "line", "column", "start_offset", "end_offset", "context", "suggestion", "metadata")
    class MetadataEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    ERROR_TYPE_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    SEVERITY_FIELD_NUMBER: _ClassVar[int]
    LINE_FIELD_NUMBER: _ClassVar[int]
    COLUMN_FIELD_NUMBER: _ClassVar[int]
    START_OFFSET_FIELD_NUMBER: _ClassVar[int]
    END_OFFSET_FIELD_NUMBER: _ClassVar[int]
    CONTEXT_FIELD_NUMBER: _ClassVar[int]
    SUGGESTION_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    error_type: str
    message: str
    severity: ValidationErrorSeverity
    line: int
    column: int
    start_offset: int
    end_offset: int
    context: str
    suggestion: str
    metadata: _containers.ScalarMap[str, str]
    def __init__(self, error_type: _Optional[str] = ..., message: _Optional[str] = ..., severity: _Optional[_Union[ValidationErrorSeverity, str]] = ..., line: _Optional[int] = ..., column: _Optional[int] = ..., start_offset: _Optional[int] = ..., end_offset: _Optional[int] = ..., context: _Optional[str] = ..., suggestion: _Optional[str] = ..., metadata: _Optional[_Mapping[str, str]] = ...) -> None: ...

class ValidateMarkdownRequest(_message.Message):
    __slots__ = ("markdown", "strict_mode")
    MARKDOWN_FIELD_NUMBER: _ClassVar[int]
    STRICT_MODE_FIELD_NUMBER: _ClassVar[int]
    markdown: str
    strict_mode: bool
    def __init__(self, markdown: _Optional[str] = ..., strict_mode: bool = ...) -> None: ...

class ValidateMarkdownResponse(_message.Message):
    __slots__ = ("success", "is_valid", "errors", "warnings", "message", "total_errors", "total_warnings", "metadata")
    class MetadataEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    IS_VALID_FIELD_NUMBER: _ClassVar[int]
    ERRORS_FIELD_NUMBER: _ClassVar[int]
    WARNINGS_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    TOTAL_ERRORS_FIELD_NUMBER: _ClassVar[int]
    TOTAL_WARNINGS_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    success: bool
    is_valid: bool
    errors: _containers.RepeatedCompositeFieldContainer[ValidationErrorMessage]
    warnings: _containers.RepeatedCompositeFieldContainer[ValidationErrorMessage]
    message: str
    total_errors: int
    total_warnings: int
    metadata: _containers.ScalarMap[str, str]
    def __init__(self, success: bool = ..., is_valid: bool = ..., errors: _Optional[_Iterable[_Union[ValidationErrorMessage, _Mapping]]] = ..., warnings: _Optional[_Iterable[_Union[ValidationErrorMessage, _Mapping]]] = ..., message: _Optional[str] = ..., total_errors: _Optional[int] = ..., total_warnings: _Optional[int] = ..., metadata: _Optional[_Mapping[str, str]] = ...) -> None: ...

class ExtractActionsRequest(_message.Message):
    __slots__ = ("text", "doc_id")
    TEXT_FIELD_NUMBER: _ClassVar[int]
    DOC_ID_FIELD_NUMBER: _ClassVar[int]
    text: str
    doc_id: str
    def __init__(self, text: _Optional[str] = ..., doc_id: _Optional[str] = ...) -> None: ...

class DependencySpanProto(_message.Message):
    __slots__ = ("span_type", "token_ids", "head_token_id", "text", "lemma_form")
    SPAN_TYPE_FIELD_NUMBER: _ClassVar[int]
    TOKEN_IDS_FIELD_NUMBER: _ClassVar[int]
    HEAD_TOKEN_ID_FIELD_NUMBER: _ClassVar[int]
    TEXT_FIELD_NUMBER: _ClassVar[int]
    LEMMA_FORM_FIELD_NUMBER: _ClassVar[int]
    span_type: str
    token_ids: _containers.RepeatedScalarFieldContainer[int]
    head_token_id: int
    text: str
    lemma_form: str
    def __init__(self, span_type: _Optional[str] = ..., token_ids: _Optional[_Iterable[int]] = ..., head_token_id: _Optional[int] = ..., text: _Optional[str] = ..., lemma_form: _Optional[str] = ...) -> None: ...

class ActionProto(_message.Message):
    __slots__ = ("action_id", "verb_lemma", "verb_text", "object_text", "full_phrase", "sentence_text", "sentence_idx", "char_start", "char_end", "modifiers", "action_score", "subject_text", "spans", "tokens", "verb_span_idx", "subject_span_idx", "object_span_idx")
    ACTION_ID_FIELD_NUMBER: _ClassVar[int]
    VERB_LEMMA_FIELD_NUMBER: _ClassVar[int]
    VERB_TEXT_FIELD_NUMBER: _ClassVar[int]
    OBJECT_TEXT_FIELD_NUMBER: _ClassVar[int]
    FULL_PHRASE_FIELD_NUMBER: _ClassVar[int]
    SENTENCE_TEXT_FIELD_NUMBER: _ClassVar[int]
    SENTENCE_IDX_FIELD_NUMBER: _ClassVar[int]
    CHAR_START_FIELD_NUMBER: _ClassVar[int]
    CHAR_END_FIELD_NUMBER: _ClassVar[int]
    MODIFIERS_FIELD_NUMBER: _ClassVar[int]
    ACTION_SCORE_FIELD_NUMBER: _ClassVar[int]
    SUBJECT_TEXT_FIELD_NUMBER: _ClassVar[int]
    SPANS_FIELD_NUMBER: _ClassVar[int]
    TOKENS_FIELD_NUMBER: _ClassVar[int]
    VERB_SPAN_IDX_FIELD_NUMBER: _ClassVar[int]
    SUBJECT_SPAN_IDX_FIELD_NUMBER: _ClassVar[int]
    OBJECT_SPAN_IDX_FIELD_NUMBER: _ClassVar[int]
    action_id: str
    verb_lemma: str
    verb_text: str
    object_text: str
    full_phrase: str
    sentence_text: str
    sentence_idx: int
    char_start: int
    char_end: int
    modifiers: _containers.RepeatedScalarFieldContainer[str]
    action_score: float
    subject_text: str
    spans: _containers.RepeatedCompositeFieldContainer[DependencySpanProto]
    tokens: _containers.RepeatedCompositeFieldContainer[UnifiedToken]
    verb_span_idx: int
    subject_span_idx: int
    object_span_idx: int
    def __init__(self, action_id: _Optional[str] = ..., verb_lemma: _Optional[str] = ..., verb_text: _Optional[str] = ..., object_text: _Optional[str] = ..., full_phrase: _Optional[str] = ..., sentence_text: _Optional[str] = ..., sentence_idx: _Optional[int] = ..., char_start: _Optional[int] = ..., char_end: _Optional[int] = ..., modifiers: _Optional[_Iterable[str]] = ..., action_score: _Optional[float] = ..., subject_text: _Optional[str] = ..., spans: _Optional[_Iterable[_Union[DependencySpanProto, _Mapping]]] = ..., tokens: _Optional[_Iterable[_Union[UnifiedToken, _Mapping]]] = ..., verb_span_idx: _Optional[int] = ..., subject_span_idx: _Optional[int] = ..., object_span_idx: _Optional[int] = ...) -> None: ...

class DependencyProto(_message.Message):
    __slots__ = ("source_id", "target_id", "marker_text", "link_score", "relation_subtype", "evidence_type")
    SOURCE_ID_FIELD_NUMBER: _ClassVar[int]
    TARGET_ID_FIELD_NUMBER: _ClassVar[int]
    MARKER_TEXT_FIELD_NUMBER: _ClassVar[int]
    LINK_SCORE_FIELD_NUMBER: _ClassVar[int]
    RELATION_SUBTYPE_FIELD_NUMBER: _ClassVar[int]
    EVIDENCE_TYPE_FIELD_NUMBER: _ClassVar[int]
    source_id: str
    target_id: str
    marker_text: str
    link_score: float
    relation_subtype: str
    evidence_type: str
    def __init__(self, source_id: _Optional[str] = ..., target_id: _Optional[str] = ..., marker_text: _Optional[str] = ..., link_score: _Optional[float] = ..., relation_subtype: _Optional[str] = ..., evidence_type: _Optional[str] = ...) -> None: ...

class ExtractActionsResponse(_message.Message):
    __slots__ = ("success", "actions", "dependencies", "message")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ACTIONS_FIELD_NUMBER: _ClassVar[int]
    DEPENDENCIES_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    success: bool
    actions: _containers.RepeatedCompositeFieldContainer[ActionProto]
    dependencies: _containers.RepeatedCompositeFieldContainer[DependencyProto]
    message: str
    def __init__(self, success: bool = ..., actions: _Optional[_Iterable[_Union[ActionProto, _Mapping]]] = ..., dependencies: _Optional[_Iterable[_Union[DependencyProto, _Mapping]]] = ..., message: _Optional[str] = ...) -> None: ...

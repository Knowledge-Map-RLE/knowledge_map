"""
Layer: Frameworks & Drivers — Infrastructure
Package: infrastructure.neo4j.orm_models
Responsibility: neomodel ORM-классы для Neo4j — детали хранилища.

Принадлежит слою Infrastructure, потому что содержит ORM-специфичный код (neomodel).
Репозитории в adapters/ используют эти классы и транслируют их в доменные dataclass-ы.

Перемещено из src/models.py. Методы бизнес-логики (link_to, _is_acyclic) удалены:
  - _is_acyclic → domain/rules/graph_acyclicity.py (чистая функция)
  - link_to → application/links/create_link.py (use case)
  - unlink → adapters/repositories/link_repository.py (репозиторий)

Allowed imports: neomodel, datetime, стандартная библиотека
Forbidden imports: fastapi, grpc, aioboto3, domain, application, adapters, web
"""
from datetime import datetime

from neomodel import (
    StructuredNode,
    StringProperty,
    IntegerProperty,
    BooleanProperty,
    RelationshipTo,
    RelationshipFrom,
    JSONProperty,
    StructuredRel,
    UniqueIdProperty,
    DateTimeProperty,
    FloatProperty,
)


class LinkRel(StructuredRel):
    """Модель отношения (связи) между блоками."""
    uid = UniqueIdProperty(primary_key=True)


class User(StructuredNode):
    """ORM-модель пользователя."""
    uid = UniqueIdProperty(primary_key=True)
    login = StringProperty(required=True, unique_index=True)
    password = StringProperty(required=True)
    nickname = StringProperty(required=True)
    data = JSONProperty()

    uploaded = RelationshipTo("PDFDocument", "UPLOADED")


class Tag(StructuredNode):
    """ORM-модель метки."""
    text = StringProperty(required=True, unique_index=True)
    block = RelationshipTo("Block", "TAGGED")


class LinkMetadata(StructuredNode):
    """ORM-модель метаданных связи."""
    uid = UniqueIdProperty()
    created_by = RelationshipFrom("User", "CREATED")
    source_id = StringProperty(index=True)
    target_id = StringProperty(index=True)


class Block(StructuredNode):
    """
    ORM-модель блока знаний.

    Методы бизнес-логики намеренно удалены из этого класса:
      - _is_acyclic() → domain/rules/graph_acyclicity.py
      - link_to() → application/links/create_link.py
      - unlink() → adapters/repositories/link_repository.py
      - get_tags() → adapters/repositories/block_repository.py
    """
    uid = UniqueIdProperty(primary_key=True)
    content = StringProperty(required=True)
    layer = IntegerProperty(index=True, default=0)
    level = IntegerProperty(index=True, default=0)
    physical_scale = IntegerProperty(index=True, default=0)
    sublevel_id = IntegerProperty(index=True, default=-1)
    is_pinned = BooleanProperty(default=False)
    data = JSONProperty()

    created_by = RelationshipFrom("User", "CREATED")
    target = RelationshipTo("Block", "LINK_TO", model=LinkRel)


class PDFDocument(StructuredNode):
    """ORM-модель PDF-документа."""
    uid = UniqueIdProperty(primary_key=True)
    original_filename = StringProperty(required=True, index=True)
    md5_hash = StringProperty(required=True, unique_index=True)
    s3_bucket = StringProperty(default="knowledge-map-data")
    s3_key = StringProperty(required=True)
    file_size = IntegerProperty()
    upload_date = DateTimeProperty(default=datetime.utcnow)

    title = StringProperty()
    authors = JSONProperty()
    abstract = StringProperty()
    keywords = JSONProperty()
    publication_date = DateTimeProperty()
    journal = StringProperty()
    doi = StringProperty()

    docling_raw_md_s3_key = StringProperty()
    formatted_md_s3_key = StringProperty()
    user_md_s3_key = StringProperty()

    source = StringProperty(default="upload")
    pubmed_id = StringProperty()
    pmc_id = StringProperty()
    is_open_access = BooleanProperty(default=False)

    is_processed = BooleanProperty(default=False)
    processing_status = StringProperty(default="uploaded")
    error_message = StringProperty()

    created_by = RelationshipFrom("User", "UPLOADED")
    annotations = RelationshipTo("PDFAnnotation", "HAS_ANNOTATION")
    markdown_annotations = RelationshipTo("MarkdownAnnotation", "HAS_MARKDOWN_ANNOTATION")


class PDFAnnotation(StructuredNode):
    """ORM-модель аннотации страницы PDF."""
    uid = UniqueIdProperty(primary_key=True)
    annotation_type = StringProperty(required=True, index=True)
    content = StringProperty(required=True)
    confidence = FloatProperty()
    page_number = IntegerProperty()
    bbox_x = FloatProperty()
    bbox_y = FloatProperty()
    bbox_width = FloatProperty()
    bbox_height = FloatProperty()
    metadata = JSONProperty()
    created_date = DateTimeProperty(default=datetime.utcnow)

    document = RelationshipFrom("PDFDocument", "HAS_ANNOTATION")
    created_by = RelationshipFrom("User", "CREATED_ANNOTATION")


class AnnotationRelationRel(StructuredRel):
    """ORM-модель отношения между Markdown-аннотациями."""
    uid = UniqueIdProperty(primary_key=True)
    relation_type = StringProperty(required=True)
    created_date = DateTimeProperty(default=datetime.utcnow)
    metadata = JSONProperty()


class MarkdownAnnotation(StructuredNode):
    """ORM-модель аннотации текста в Markdown-документе."""
    uid = UniqueIdProperty(primary_key=True)
    text = StringProperty(required=True)
    annotation_type = StringProperty(required=True, index=True)
    start_offset = IntegerProperty(required=True)
    end_offset = IntegerProperty(required=True)
    color = StringProperty(default="#ffeb3b")
    metadata = JSONProperty()
    confidence = FloatProperty()
    created_date = DateTimeProperty(default=datetime.utcnow)
    source = StringProperty(default="user", index=True)
    processor_version = StringProperty()

    document = RelationshipFrom("PDFDocument", "HAS_MARKDOWN_ANNOTATION")
    created_by = RelationshipFrom("User", "CREATED_MARKDOWN_ANNOTATION")
    relations_to = RelationshipTo(
        "MarkdownAnnotation", "RELATES_TO", model=AnnotationRelationRel
    )
    relations_from = RelationshipFrom(
        "MarkdownAnnotation", "RELATES_TO", model=AnnotationRelationRel
    )
    linguistic_patterns = RelationshipFrom("LinguisticPattern", "FOUND_IN")


class LabelStudioProject(StructuredNode):
    """ORM-модель проекта Label Studio."""
    uid = UniqueIdProperty(primary_key=True)
    name = StringProperty(required=True)
    description = StringProperty()
    label_config = StringProperty(required=True)
    is_active = BooleanProperty(default=True)
    created_date = DateTimeProperty(default=datetime.utcnow)

    created_by = RelationshipFrom("User", "CREATED_PROJECT")
    documents = RelationshipTo("PDFDocument", "USES_PROJECT")


class LinguisticPatternRel(StructuredRel):
    """Связь DEP_RELATION между узлами LexicalForm (лингвистическая зависимость)."""
    relation_type = StringProperty(required=True)
    doc_id = StringProperty(index=True)
    annotation_uid = StringProperty(index=True)


class LexicalForm(StructuredNode):
    """Словоформа с частью речи — узел лингвистического паттерна."""
    uid = UniqueIdProperty(primary_key=True)
    text = StringProperty(required=True)
    lemma = StringProperty()
    pos = StringProperty(index=True)       # VERB, NOUN, ADJ …
    pos_fine = StringProperty()            # VBD, NN, JJ …
    doc_id = StringProperty(index=True)
    annotation_uid = StringProperty(index=True)

    dep_relation_to = RelationshipTo(
        "LexicalForm", "DEP_RELATION", model=LinguisticPatternRel
    )
    part_of = RelationshipTo("LinguisticPattern", "PART_OF")


class LinguisticPattern(StructuredNode):
    """Лингвистический паттерн, извлечённый из аннотации документа."""
    uid = UniqueIdProperty(primary_key=True)
    pattern_str = StringProperty(required=True, index=True)
    pattern_type = StringProperty(required=True, index=True)
    annotation_type = StringProperty(required=True, index=True)
    frequency = IntegerProperty(default=1)
    doc_id = StringProperty(index=True)

    found_in = RelationshipTo("MarkdownAnnotation", "FOUND_IN")
    lexical_forms = RelationshipFrom("LexicalForm", "PART_OF")

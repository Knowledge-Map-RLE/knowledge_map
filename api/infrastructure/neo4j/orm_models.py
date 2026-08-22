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
    ArrayProperty,
)


class LinkRel(StructuredRel):
    """Модель отношения (связи) между блоками."""
    uid = UniqueIdProperty(primary_key=True)


class Tag(StructuredNode):
    """ORM-модель метки."""
    text = StringProperty(required=True, unique_index=True)
    block = RelationshipTo("Block", "TAGGED")


class LinkMetadata(StructuredNode):
    """ORM-модель метаданных связи."""
    uid = UniqueIdProperty()
    created_by_uid = StringProperty()
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

    created_by_uid = StringProperty()
    target = RelationshipTo("Block", "LINK_TO", model=LinkRel)


class ArticleBlock(StructuredNode):
    """
    Структурный блок статьи (редактор article_editor).

    Блок — единица структурированного представления статьи:
    T1 (заголовок), T14 (эксперимент), T18 (вмешательство),
    T19 (организм/вид), T55 (группа), T56 (шаг эксперимента).
    data хранится как JSON-строка (Neo4j не поддерживает вложенные map
    в качестве свойств — только примитивы и массивы примитивов).
    """
    uid = StringProperty(primary_key=True)          # instanceId блока
    block_type = IntegerProperty(required=True, index=True)
    data = StringProperty(default="{}")             # JSON-строка
    order = IntegerProperty(default=0, index=True)
    created_by_uid = StringProperty()

    document = RelationshipFrom("Document", "HAS_BLOCK")


class Document(StructuredNode):
    """ORM-модель документа — объединяет PDFDocument и Article."""
    uid = StringProperty(primary_key=True)
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

    source = StringProperty(default="upload")  # upload / pubmed / pmc / ncbi
    pubmed_id = StringProperty()
    pmc_id = StringProperty()
    is_open_access = BooleanProperty(default=False)

    is_processed = BooleanProperty(default=False)
    processing_status = StringProperty(default="uploaded")
    error_message = StringProperty()

    has_full_text = BooleanProperty(default=False, index=True)

    created_by_uid = StringProperty()
    annotations = RelationshipTo("PDFAnnotation", "HAS_ANNOTATION")
    markdown_annotations = RelationshipTo("MarkdownAnnotation", "HAS_MARKDOWN_ANNOTATION")
    blocks = RelationshipTo("ArticleBlock", "HAS_BLOCK")


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

    document = RelationshipFrom("Document", "HAS_ANNOTATION")
    created_by_uid = StringProperty()


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

    document = RelationshipFrom("Document", "HAS_MARKDOWN_ANNOTATION")
    created_by_uid = StringProperty()
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

    created_by_uid = StringProperty()
    documents = RelationshipTo("Document", "USES_PROJECT")


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
    pos = StringProperty(index=True)
    pos_fine = StringProperty()
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


class LeadsToRel(StructuredRel):
    """Отношение LEADS_TO между Action→Action."""
    relation_subtype = StringProperty()   # causes|enables|prevents|via_mechanism|sequential
    confidence = FloatProperty(default=1.0)
    evidence = ArrayProperty(StringProperty())
    doc_id = StringProperty(index=True)
    status = StringProperty(default="pending")  # pending | confirmed | rejected


class SyntacticDepRel(StructuredRel):
    """Синтаксическая зависимость между Action→Action (xcomp/advcl/ccomp/conj).
    Отдельный тип ребра — не является причинно-следственной связью LEADS_TO.
    """
    dep_label = StringProperty()      # xcomp | advcl | ccomp | conj
    confidence = FloatProperty(default=1.0)
    doc_id = StringProperty(index=True)


class Action(StructuredNode):
    """Действие (глаголь / номинализация / биомедицинская сущность), извлечённое из аннотации.

    Хранит полную лингвистическую структуру (токены, спаны) в JSON-полях.
    Поля verb, label_text — кэши для быстрого доступа и индексации.
    Старые поля (verb_text, subject, object_) оставлены для обратной совместимости
    на период миграции — будут удалены после запуска migrate_action_linguistics.py.
    """
    uid = UniqueIdProperty(primary_key=True)

    # Кэш для быстрого доступа / индексации
    verb = StringProperty(required=True, index=True)       # лемма глагола (из verb_span)
    label_text = StringProperty(index=True)                 # "Rapamycin inhibits mTOR"

    # Полная лингвистическая структура — JSON-сериализация
    tokens_json = StringProperty()                          # LinguisticToken[]
    spans_json = StringProperty()                           # DependencySpan[]

    # Кэш рендеринга (из JSON, но быстрый доступ без десериализации)
    verb_text = StringProperty()                            # оригинальная форма глагола
    subject = StringProperty()                              # текст подлежащего
    object_ = StringProperty(db_property="object")          # текст дополнения

    # Метаданные
    sentence_text = StringProperty()
    char_start = IntegerProperty()
    char_end = IntegerProperty()
    doc_id = StringProperty(index=True)
    annotation_uid = StringProperty(index=True)
    action_class = StringProperty(default="action")         # "action" | "result" | "mechanism"
    norm_key = StringProperty(index=True)                   # sha256[:16] нормализованного

    # Индексы ключевых спанов в spans_json
    verb_span_idx = IntegerProperty(default=-1)
    subject_span_idx = IntegerProperty(default=-1)
    object_span_idx = IntegerProperty(default=-1)

    leads_to_action = RelationshipTo("Action", "LEADS_TO", model=LeadsToRel)
    syntactic_dep = RelationshipTo("Action", "SYNTACTIC_DEP", model=SyntacticDepRel)
    lexical_units = RelationshipFrom("LexicalUnit", "PART_OF")


class PartOfRel(StructuredRel):
    """Связь LexicalUnit → Action (токен является частью действия)."""
    doc_id = StringProperty(index=True)
    token_index = IntegerProperty()  # id токена в предложении


class DependsOnRel(StructuredRel):
    """Синтаксическая зависимость LexicalUnit → LexicalUnit."""
    dep_label = StringProperty(required=True, index=True)  # nsubj, dobj, amod, ...
    doc_id = StringProperty(index=True)


class LexicalUnit(StructuredNode):
    """
    Лексическая единица — отдельный токен (слово) с лингвистическими атрибутами.

    Узел в графе для полнотекстового лингвистического поиска.
    Связывается с Action через PART_OF, между собой — через DEPENDS_ON.
    """
    uid = UniqueIdProperty(primary_key=True)
    text = StringProperty(required=True)
    lemma = StringProperty(required=True, index=True)
    pos = StringProperty(required=True, index=True)
    pos_fine = StringProperty()
    dep = StringProperty(index=True)
    is_stop = BooleanProperty(default=False)
    is_punct = BooleanProperty(default=False)
    doc_id = StringProperty(index=True)

    # Связи
    part_of_action = RelationshipTo("Action", "PART_OF", model=PartOfRel)
    depends_on = RelationshipTo("LexicalUnit", "DEPENDS_ON", model=DependsOnRel)
    depended_by = RelationshipFrom("LexicalUnit", "DEPENDS_ON", model=DependsOnRel)


# =============================================================================
# Pattern — паттерн как граф Action + LexicalUnit
# =============================================================================


class PatternContainsNodeRel(StructuredRel):
    """
    Связь Pattern → Action / Pattern → LexicalUnit.

    Хранит семантическую роль узла внутри паттерна и порядок.
    """
    role = StringProperty(required=True)          # verb, subject, object, modifier, compound, connector
    node_type = StringProperty(required=True)     # Action, LexicalUnit
    original_index = IntegerProperty(default=0)   # порядок в каноническом графе
    doc_id = StringProperty(index=True)


class PatternContainsEdgeRel(StructuredRel):
    """
    Мета-связь, описывающая ребро внутри паттерна.

    Pattern-узел хранит рёбра как свойства связей к самому себе (self-loops)
    или через отдельный узел PatternEdge. Для простоты используем JSON-свойство
    на Pattern, а этот Rel — для связей Pattern → Pattern (перекрытие).
    """
    edge_type = StringProperty(required=True)     # LEADS_TO, DEPENDS_ON, PART_OF
    relation_subtype = StringProperty()           # enables, nsubj, dobj, ...
    source_node_id = StringProperty()             # uid исходного узла паттерна
    target_node_id = StringProperty()             # uid целевого узла паттерна


class Pattern(StructuredNode):
    """
    Паттерн — отдельная модель в БД с собственным UID.

    Паттерн — это граф из Action и LexicalUnit, связанных рёбрами
    LEADS_TO, DEPENDS_ON, PART_OF. Масштаб: от 1 узла до ~100.

    Хранит:
      - Каноническую структуру (узлы + рёбра) через связи CONTAINS_NODE
      - Статистику (frequency, stability, doc_count)
      - pattern_hash для дедупликации
      - edges_json — JSON-массив рёбер паттерна (source_id, target_id, edge_type, relation_subtype)
    """
    uid = UniqueIdProperty(primary_key=True)
    name = StringProperty(default="")
    description = StringProperty(default="")
    pattern_hash = StringProperty(index=True)     # SHA256[:16] канонической структуры
    frequency = IntegerProperty(default=1)         # общее число вхождений
    stability = FloatProperty(default=0.0)         # docs_with_pattern / total_occurrences
    doc_count = IntegerProperty(default=0)         # число уникальных документов
    node_count = IntegerProperty(default=0)        # число узлов в каноническом графе
    edge_count = IntegerProperty(default=0)        # число рёбер в каноническом графе
    size_category = StringProperty()               # unigram, small, medium, large, xlarge
    created_date = DateTimeProperty(default=datetime.utcnow)

    # Рёбра паттерна хранятся как JSON (для компактности)
    edges_json = StringProperty()                  # JSON-массив {source_id, target_id, edge_type, relation_subtype}

    # Связи к реальным узлам Action и LexicalUnit
    contains_actions = RelationshipTo(
        "Action", "CONTAINS_NODE", model=PatternContainsNodeRel
    )
    contains_lexical = RelationshipTo(
        "LexicalUnit", "CONTAINS_NODE", model=PatternContainsNodeRel
    )

    # Конкретные вхождения паттерна (Pattern → Pattern через FOUND_AS)
    # Каждое вхождение — отдельный Pattern с is_instance=True
    found_as = RelationshipTo("Pattern", "FOUND_AS")


# =============================================================================
# AI Chat — персистентные диалоги с ассистентом (учёт токенов и стоимости)
# =============================================================================


class AIChat(StructuredNode):
    """ORM-модель AI-чата пользователя."""
    uid = UniqueIdProperty(primary_key=True)
    user_uid = StringProperty(required=True, index=True)
    title = StringProperty(default="")
    model = StringProperty(default="")
    created_at = DateTimeProperty(default=datetime.utcnow)
    updated_at = DateTimeProperty(default=datetime.utcnow)

    messages = RelationshipTo("AIMessage", "HAS_MESSAGE")


class AIMessage(StructuredNode):
    """ORM-модель сообщения в AI-чате."""
    uid = UniqueIdProperty(primary_key=True)
    role = StringProperty(required=True)  # user | assistant | system
    content = StringProperty(required=True)
    order = IntegerProperty(default=0, index=True)
    created_at = DateTimeProperty(default=datetime.utcnow)

    chat = RelationshipFrom("AIChat", "HAS_MESSAGE")
    usage = RelationshipTo("AIUsage", "HAS_USAGE")


class AIUsage(StructuredNode):
    """ORM-модель учёта токенов и стоимости одного AI-запроса.

    Стоимости хранятся строками — точное Decimal-представление (8 знаков),
    без float. ``provider_request_id`` — id ответа провайдера для
    идемпотентного списания кредитов через billing.
    """
    uid = UniqueIdProperty(primary_key=True)
    message_uid = StringProperty(required=True, index=True)
    chat_uid = StringProperty(required=True, index=True)
    user_uid = StringProperty(required=True, index=True)
    model = StringProperty(default="")
    provider_request_id = StringProperty(required=True, unique_index=True)

    estimated_input_tokens = IntegerProperty(default=0)
    estimated_output_tokens = IntegerProperty(default=0)
    estimated_cached_tokens = IntegerProperty()
    estimated_cost = StringProperty(default="0")
    estimated_currency = StringProperty(default="RUB")

    actual_input_tokens = IntegerProperty(default=0)
    actual_cached_tokens = IntegerProperty(default=0)
    actual_output_tokens = IntegerProperty(default=0)
    actual_tool_tokens = IntegerProperty(default=0)
    actual_cost = StringProperty(default="0")
    actual_currency = StringProperty(default="RUB")

    created_at = DateTimeProperty(default=datetime.utcnow)

    message = RelationshipFrom("AIMessage", "HAS_USAGE")

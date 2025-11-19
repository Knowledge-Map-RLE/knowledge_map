from collections import deque
from neomodel import (
    StructuredNode, StringProperty, IntegerProperty, BooleanProperty,
    RelationshipTo, RelationshipFrom, JSONProperty, config,
    StructuredRel, UniqueIdProperty, DateTimeProperty, FloatProperty
)
# from uuid_v6_property import UUIDv6Property # Больше не используем
from datetime import datetime

from services.config import settings

# Настройка DATABASE_URL будет выполнена в app.py

class LinkRel(StructuredRel):
    """Модель отношения (связи) между блоками"""
    uid = UniqueIdProperty(primary_key=True)


class User(StructuredNode):
    """Модель пользователя"""
    
    uid = UniqueIdProperty(primary_key=True)
    """Уникальный идентификатор. Содержит время создания"""
    login = StringProperty(required=True, unique_index=True)
    """Логин"""
    password = StringProperty(required=True)
    """Пароль"""
    nickname = StringProperty(required=True)
    """Прозвище — отображаемое имя"""
    # surname = StringProperty()
    # """Фамилия"""
    # given_names = StringProperty()
    # """Имя"""
    data = JSONProperty()
    """Нестандартные данные — свойство для любых других не предусмотренных данных"""
    
    # Отношения
    uploaded = RelationshipTo('PDFDocument', 'UPLOADED')
    """PDF документы, загруженные пользователем"""

class Tag(StructuredNode):
    """Модель метки"""
    
    # Свойства
    text = StringProperty(required=True, unique_index=True)
    """Текст метки"""
    
    # Отношения
    block = RelationshipTo('Block', 'TAGGED')
    """Блоки, которые имеют эту метку"""

class LinkMetadata(StructuredNode):
    """Модель метаданных связи"""
    
    # Свойства
    uid = UniqueIdProperty()
    """Уникальный идентификатор. Содержит время создания"""
    created_by = RelationshipFrom('User', 'CREATED')
    """Создатель"""
    source_id = StringProperty(index=True)
    target_id = StringProperty(index=True)

class Block(StructuredNode):
    """Модель блока"""
    
    # Свойства
    uid = UniqueIdProperty(primary_key=True)
    """Уникальный идентификатор. Содержит время создания"""
    content = StringProperty(required=True)
    """Содержимое"""
    layer = IntegerProperty(index=True, default=0)
    """Слой"""
    level = IntegerProperty(index=True, default=0)
    """Уровень"""
    physical_scale = IntegerProperty(index=True, default=0)
    """Физический масштаб уровня в метрах (степень числа 10). По умолчанию 0 означает 10^0 = 1 метр"""
    sublevel_id = IntegerProperty(index=True, default=-1)
    """ID подуровня, к которому принадлежит блок"""
    is_pinned = BooleanProperty(default=False)
    """Закреплен ли блок за уровнем"""
    
    data = JSONProperty()
    """Нестандартные данные — свойство для любых других не предусмотренных данных"""

    # Отношения
    created_by = RelationshipFrom('User', 'CREATED')
    """Создатель"""
    target = RelationshipTo('Block', 'LINK_TO', model=LinkRel)
    """
    Целевой блок. Обратные связи в Neo4j строятся автоматически —
    отдельно создавать source или модель связей Link не нужно
    """
    
    def _is_acyclic(self, target):
        """
        Итеративная (не рекурсивная) проверка ацикличности графа при добавлении новой связи
        с использованием стека, встроенная в API микросервис (не из микросервиса бизнес логики)
        """
        
        visited = set()
        path = set()
        stack = deque([(target, False)])  # (node, is_processed)
        
        while stack:
            node, is_processed = stack.pop()
            
            if is_processed:
                # Удаляем узел из текущего пути
                path.discard(node.id)
                continue
            
            if node.id == self.id:
                return False # Найден цикл через новую связь
                
            if node.id in path:
                return False # Найден цикл
                
            if node.id in visited:
                continue
                
            visited.add(node.id)
            path.add(node.id)
            
            # Добавляем узел обратно в стек как обработанный
            stack.append((node, True))
            
            # Добавляем все исходящие связи в стек
            for rel in node.target.all():
                stack.append((rel, False))
                
        return True # Циклов не найдено
    
    def link_to(self, target, user):
        if not self._is_acyclic(target):
            raise ValueError("Создание связи приведет к циклу в графе")
        
        # 1. Создать прямую связь
        self.target.connect(target)
        # 2. Создать метаданные
        meta = LinkMetadata(
            source_id=self.id,
            target_id=target.id
        ).save()
        meta.created_by.connect(user)
        return meta
    
    # Метаданные в отдельной таблице по ID
    def get_link(self, target):
        return LinkMetadata.nodes.filter(
            source_id=self.id,
            target_id=target.id
        ).first()
    
    def unlink(self, target):
        # 1. Удалить прямую связь
        self.target.disconnect(target)
        # 2. Удалить метаданные
        meta = self.get_link(target)
        if meta:
            meta.delete()
    
    def get_tags(self) -> list[Tag]:
        """Получить все теги этого блока"""
        return Tag.nodes.filter(block=self)


class PDFDocument(StructuredNode):
    """Модель PDF документа"""
    
    # Основные свойства
    uid = UniqueIdProperty(primary_key=True)
    """Уникальный идентификатор документа"""
    original_filename = StringProperty(required=True, index=True)
    """Оригинальное имя файла"""
    md5_hash = StringProperty(required=True, unique_index=True)
    """MD5 хеш содержимого файла"""
    s3_bucket = StringProperty(default="knowledge-map-pdfs")
    """S3 bucket для хранения файла"""
    s3_key = StringProperty(required=True)
    """S3 ключ (путь) к файлу"""
    file_size = IntegerProperty()
    """Размер файла в байтах"""
    upload_date = DateTimeProperty(default=datetime.utcnow)
    """Дата загрузки"""
    
    # Метаданные документа
    title = StringProperty()
    """Заголовок документа"""
    authors = JSONProperty()
    """Список авторов"""
    abstract = StringProperty()
    """Аннотация"""
    keywords = JSONProperty()
    """Ключевые слова"""
    publication_date = DateTimeProperty()
    """Дата публикации"""
    journal = StringProperty()
    """Название журнала"""
    doi = StringProperty()
    """DOI документа"""
    
    # Markdown файлы
    docling_raw_md_s3_key = StringProperty()
    """S3 ключ к сырому Markdown от Docling (immutable)"""
    formatted_md_s3_key = StringProperty()
    """S3 ключ к AI-форматированному Markdown (immutable, initial version)"""
    user_md_s3_key = StringProperty()
    """S3 ключ к пользовательской версии Markdown (создается при первом save)"""

    # Статус обработки
    is_processed = BooleanProperty(default=False)
    """Обработан ли документ"""
    processing_status = StringProperty(default="uploaded")
    """Статус обработки: uploaded, processing, annotated, error"""
    error_message = StringProperty()
    """Сообщение об ошибке при обработке"""
    
    # Отношения
    created_by = RelationshipFrom('User', 'UPLOADED')
    """Пользователь, загрузивший документ"""
    annotations = RelationshipTo('PDFAnnotation', 'HAS_ANNOTATION')
    """Аннотации документа"""
    markdown_annotations = RelationshipTo('MarkdownAnnotation', 'HAS_MARKDOWN_ANNOTATION')
    """Markdown аннотации документа"""
    
    def get_s3_url(self) -> str:
        """Получить S3 URL для файла"""
        return f"s3://{self.s3_bucket}/{self.s3_key}"

    def get_active_markdown_key(self) -> str:
        """
        Получить ключ активной версии Markdown

        Логика выбора:
        1. Если пользователь сохранил свою версию - использовать user_md_s3_key
        2. Иначе - использовать formatted_md_s3_key (AI-форматированная версия)
        3. Если formatted_md_s3_key нет - использовать docling_raw_md_s3_key (fallback)

        Returns:
            str: S3 ключ активной версии Markdown
        """
        if self.user_md_s3_key:
            return self.user_md_s3_key
        elif self.formatted_md_s3_key:
            return self.formatted_md_s3_key
        else:
            return self.docling_raw_md_s3_key

    def get_annotations_by_type(self, annotation_type: str) -> list:
        """Получить аннотации определенного типа"""
        return [ann for ann in self.annotations.all() if ann.annotation_type == annotation_type]


class PDFAnnotation(StructuredNode):
    """Модель аннотации PDF документа"""
    
    # Основные свойства
    uid = UniqueIdProperty(primary_key=True)
    """Уникальный идентификатор аннотации"""
    annotation_type = StringProperty(required=True, index=True)
    """Тип аннотации: title, author, abstract, keyword, number, date, image, table, graph, formula, entity, action"""
    content = StringProperty(required=True)
    """Содержимое аннотации"""
    confidence = FloatProperty()
    """Уверенность модели в аннотации (0.0-1.0)"""
    
    # Позиция в документе
    page_number = IntegerProperty()
    """Номер страницы"""
    bbox_x = FloatProperty()
    """X координата bounding box"""
    bbox_y = FloatProperty()
    """Y координата bounding box"""
    bbox_width = FloatProperty()
    """Ширина bounding box"""
    bbox_height = FloatProperty()
    """Высота bounding box"""
    
    # Дополнительные метаданные
    metadata = JSONProperty()
    """Дополнительные метаданные аннотации"""
    created_date = DateTimeProperty(default=datetime.utcnow)
    """Дата создания аннотации"""
    
    # Отношения
    document = RelationshipFrom('PDFDocument', 'HAS_ANNOTATION')
    """Документ, к которому относится аннотация"""
    created_by = RelationshipFrom('User', 'CREATED_ANNOTATION')
    """Пользователь или система, создавшая аннотацию"""
    
    def get_bbox(self) -> dict:
        """Получить bounding box как словарь"""
        return {
            'x': self.bbox_x,
            'y': self.bbox_y,
            'width': self.bbox_width,
            'height': self.bbox_height
        }
    
    def set_bbox(self, x: float, y: float, width: float, height: float):
        """Установить bounding box"""
        self.bbox_x = x
        self.bbox_y = y
        self.bbox_width = width
        self.bbox_height = height


class AnnotationRelationRel(StructuredRel):
    """Модель отношения между аннотациями Markdown"""
    uid = UniqueIdProperty(primary_key=True)
    """Уникальный идентификатор отношения"""
    relation_type = StringProperty(required=True)
    """Тип связи (произвольная строка, задаваемая пользователем)"""
    created_date = DateTimeProperty(default=datetime.utcnow)
    """Дата создания связи"""
    metadata = JSONProperty()
    """Дополнительные метаданные связи"""


class MarkdownAnnotation(StructuredNode):
    """Модель аннотации текста в Markdown документе"""

    # Основные свойства
    uid = UniqueIdProperty(primary_key=True)
    """Уникальный идентификатор аннотации"""
    text = StringProperty(required=True)
    """Аннотируемый текст"""
    annotation_type = StringProperty(required=True, index=True)
    """Тип аннотации: Существительное, Глагол, Прилагательное, Подлежащее, Сказуемое, Ген, Белок, и т.д."""

    # Позиция в тексте
    start_offset = IntegerProperty(required=True)
    """Начальная позиция в тексте (индекс символа)"""
    end_offset = IntegerProperty(required=True)
    """Конечная позиция в тексте (индекс символа)"""

    # Визуализация
    color = StringProperty(default="#ffeb3b")
    """Цвет выделения аннотации в hex формате"""

    # Метаданные
    metadata = JSONProperty()
    """Дополнительные метаданные аннотации"""
    confidence = FloatProperty()
    """Уверенность NLP модели в аннотации (0.0-1.0), если применимо"""
    created_date = DateTimeProperty(default=datetime.utcnow)
    """Дата создания аннотации"""
    source = StringProperty(default="user", index=True)
    """Источник аннотации: user (пользователь), spacy (spaCy), custom (кастомная модель)"""
    processor_version = StringProperty()
    """Версия процессора, создавшего аннотацию (например, 'spacy-3.8.7_en_core_web_trf')"""

    # Отношения
    document = RelationshipFrom('PDFDocument', 'HAS_MARKDOWN_ANNOTATION')
    """Документ, к которому относится аннотация"""
    created_by = RelationshipFrom('User', 'CREATED_MARKDOWN_ANNOTATION')
    """Пользователь, создавший аннотацию"""
    relations_to = RelationshipTo('MarkdownAnnotation', 'RELATES_TO', model=AnnotationRelationRel)
    """Связи с другими аннотациями (исходящие)"""
    relations_from = RelationshipFrom('MarkdownAnnotation', 'RELATES_TO', model=AnnotationRelationRel)
    """Связи с другими аннотациями (входящие)"""

    def get_position(self) -> dict:
        """Получить позицию аннотации в тексте"""
        return {
            'start': self.start_offset,
            'end': self.end_offset
        }

    def create_relation(self, target_annotation, relation_type: str):
        """Создать связь с другой аннотацией"""
        return self.relations_to.connect(
            target_annotation,
            {
                'relation_type': relation_type,
                'created_date': datetime.utcnow()
            }
        )

    def get_all_relations(self) -> list:
        """Получить все связи аннотации (входящие и исходящие)"""
        outgoing = [
            {
                'source_uid': self.uid,
                'target_uid': rel.uid,
                'relation_type': self.relations_to.relationship(rel).relation_type,
                'direction': 'outgoing'
            }
            for rel in self.relations_to.all()
        ]
        incoming = [
            {
                'source_uid': rel.uid,
                'target_uid': self.uid,
                'relation_type': self.relations_from.relationship(rel).relation_type,
                'direction': 'incoming'
            }
            for rel in self.relations_from.all()
        ]
        return outgoing + incoming


class LabelStudioProject(StructuredNode):
    """Модель проекта Label Studio"""

    # Основные свойства
    uid = UniqueIdProperty(primary_key=True)
    """Уникальный идентификатор проекта"""
    name = StringProperty(required=True)
    """Название проекта"""
    description = StringProperty()
    """Описание проекта"""
    label_config = StringProperty(required=True)
    """Конфигурация разметки в формате XML"""

    # Статус
    is_active = BooleanProperty(default=True)
    """Активен ли проект"""
    created_date = DateTimeProperty(default=datetime.utcnow)
    """Дата создания проекта"""

    # Отношения
    created_by = RelationshipFrom('User', 'CREATED_PROJECT')
    """Создатель проекта"""
    documents = RelationshipTo('PDFDocument', 'USES_PROJECT')
    """Документы, использующие этот проект"""

    def get_label_config_xml(self) -> str:
        """Получить XML конфигурацию для Label Studio"""
        return self.label_config
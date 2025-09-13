from collections import deque
from neomodel import (
    StructuredNode, StringProperty, IntegerProperty, BooleanProperty,
    RelationshipTo, RelationshipFrom, JSONProperty, config,
    StructuredRel, UniqueIdProperty, DateTimeProperty, FloatProperty
)
# from uuid_v6_property import UUIDv6Property # Больше не используем
from datetime import datetime

from config import settings


config.DATABASE_URL = settings.get_database_url()

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
    
    def get_s3_url(self) -> str:
        """Получить S3 URL для файла"""
        return f"s3://{self.s3_bucket}/{self.s3_key}"
    
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
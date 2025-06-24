from collections import deque
from neomodel import (
    StructuredNode, StringProperty, IntegerProperty, BooleanProperty,
    RelationshipTo, RelationshipFrom, JSONProperty, config,
    StructuredRel, UniqueIdProperty
)
# from uuid_v6_property import UUIDv6Property # Больше не используем

from config import settings


config.DATABASE_URL = settings.get_database_url()

class LinkRel(StructuredRel):
    """Модель отношения (связи) между блоками"""
    uid = UniqueIdProperty(primary_key=True)


class User(StructuredNode):
    """Модель пользователя"""
    
    # Свойства
    uid = UniqueIdProperty(primary_key=True)
    """Уникальный идентификатор. Содержит время создания"""
    login = StringProperty(required=True, unique_index=True)
    """Логин"""
    password = StringProperty(required=True)
    """Пароль"""
    nickname = StringProperty(required=True)
    """Прозвище — отображаемое имя"""
    surname = StringProperty()
    """Фамилия"""
    given_names = StringProperty()
    """Имя"""
    
    data = JSONProperty()
    """Нестандартные данные — свойство для любых других не предусмотренных данных"""

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
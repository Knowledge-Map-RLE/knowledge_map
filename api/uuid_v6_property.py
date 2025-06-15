from neomodel import StringProperty
from uuid6 import uuid6
from uuid import UUID

class UUIDv6Property(StringProperty):
    """
    Упрощенное свойство для UUID v6 на базе StringProperty
    """
    
    def __init__(self, **kwargs):
        kwargs.setdefault('unique_index', True)
        kwargs.setdefault('default', self.default_value)
        super().__init__(**kwargs)
    
    def default_value(self):
        """Генерирует UUID v6 как строку"""
        return str(uuid6())
    
    def deflate(self, value, obj=None, skip_empty=False):
        """Валидация и преобразование"""
        if value is None:
            return None
        if isinstance(value, (str, UUID)):
            # Валидируем UUID
            try:
                UUID(str(value))
                return str(value)
            except ValueError:
                raise ValueError(f"Invalid UUID: {value}")
        raise ValueError(f"UUIDv6Property expects UUID or string, got {type(value)}")
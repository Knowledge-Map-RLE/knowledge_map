from datetime import datetime, timedelta
from typing import Optional, List
from neomodel import (
    StructuredNode, StringProperty, IntegerProperty, BooleanProperty,
    DateTimeProperty, JSONProperty, UniqueIdProperty, config
)
from .config import settings

# Настройка подключения к Neo4j
# neomodel ожидает формат: bolt://user:password@host:port
_hostport = settings.NEO4J_URI.replace("bolt://", "")
config.DATABASE_URL = f"bolt://{settings.NEO4J_USER}:{settings.NEO4J_PASSWORD}@{_hostport}"


class User(StructuredNode):
    """Модель пользователя"""
    
    uid = UniqueIdProperty(primary_key=True)
    """Уникальный идентификатор"""
    
    login = StringProperty(required=True, unique_index=True)
    """Логин пользователя"""
    
    password_hash = StringProperty(required=True)
    """Хеш пароля"""
    
    nickname = StringProperty(required=True)
    """Отображаемое имя"""
    
    is_active = BooleanProperty(default=True)
    """Активен ли пользователь"""
    
    is_2fa_enabled = BooleanProperty(default=False)
    """Включена ли двухфакторная аутентификация"""
    
    two_fa_secret = StringProperty()
    """Секрет для 2FA"""
    
    recovery_keys = JSONProperty(default=list)
    """Ключи восстановления"""
    
    created_at = DateTimeProperty(default=datetime.utcnow)
    """Дата создания"""
    
    last_login = DateTimeProperty()
    """Последний вход"""
    
    login_attempts = IntegerProperty(default=0)
    """Количество неудачных попыток входа"""
    
    locked_until = DateTimeProperty()
    """Время блокировки аккаунта"""
    
    data = JSONProperty()
    """Дополнительные данные"""


class Session(StructuredNode):
    """Модель сессии пользователя"""
    
    uid = UniqueIdProperty(primary_key=True)
    """Уникальный идентификатор сессии"""
    
    user_id = StringProperty(required=True, index=True)
    """ID пользователя"""
    
    token = StringProperty(required=True, unique_index=True)
    """JWT токен"""
    
    device_info = JSONProperty()
    """Информация об устройстве"""
    
    ip_address = StringProperty()
    """IP адрес"""
    
    created_at = DateTimeProperty(default=datetime.utcnow)
    """Дата создания сессии"""
    
    expires_at = DateTimeProperty(required=True)
    """Дата истечения сессии"""
    
    is_active = BooleanProperty(default=True)
    """Активна ли сессия""" 
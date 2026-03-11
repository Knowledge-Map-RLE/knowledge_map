"""
Layer: Interface Adapters — Repository
Package: adapters.repositories.user_repository
Responsibility: neomodel-реализация UserRepositoryProtocol.

Allowed imports: neomodel, infrastructure.neo4j.orm_models, domain.models.user, domain.exceptions
Forbidden imports: fastapi, web
"""
from __future__ import annotations

from typing import Optional

from neomodel import DoesNotExist

from infrastructure.neo4j.orm_models import User as OrmUser
from domain.models.user import User
from domain.exceptions import NotFoundError


def _orm_to_domain(orm_user: OrmUser) -> User:
    return User(uid=orm_user.uid, login=orm_user.login, nickname=orm_user.nickname, data=orm_user.data)


class UserRepository:
    """
    neomodel-реализация репозитория пользователей.
    Удовлетворяет UserRepositoryProtocol (structural subtyping).
    """

    def get_by_id(self, uid: str) -> Optional[User]:
        try:
            return _orm_to_domain(OrmUser.nodes.get(uid=uid))
        except DoesNotExist:
            return None

    def get_or_create_test_user(self) -> User:
        """Возвращает тестового пользователя или создаёт нового."""
        try:
            orm_user = OrmUser.nodes.get(login="test_user")
        except DoesNotExist:
            orm_user = OrmUser(
                login="test_user", password="test", nickname="Test User"
            ).save()
        return _orm_to_domain(orm_user)

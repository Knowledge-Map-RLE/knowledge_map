"""
Layer: Application (Use Cases)
Package: application.links.delete_link
Responsibility: Удаляет связь между блоками по её ID.

Allowed imports: domain.exceptions, application.ports.repositories
Forbidden imports: fastapi, neomodel, infrastructure, web
"""
from __future__ import annotations

from application.ports.repositories import LinkRepositoryProtocol


def delete_link(repo: LinkRepositoryProtocol, link_id: str) -> None:
    """
    Удаляет связь по link_id.

    Raises:
        NotFoundError: связь не найдена.
    """
    repo.delete_by_id(link_id)

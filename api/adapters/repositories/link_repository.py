"""
Layer: Interface Adapters — Repository
Package: adapters.repositories.link_repository
Responsibility: neomodel-реализация LinkRepositoryProtocol.

Allowed imports: neomodel, infrastructure.neo4j.orm_models, domain.models.block, domain.exceptions
Forbidden imports: fastapi, web
"""
from __future__ import annotations

import logging
from typing import Optional

from neomodel import db, DoesNotExist

from infrastructure.neo4j.orm_models import Block as OrmBlock, LinkMetadata
from domain.models.block import LinkRecord
from domain.exceptions import NotFoundError

logger = logging.getLogger(__name__)


class LinkRepository:
    """
    neomodel-реализация репозитория связей.
    Удовлетворяет LinkRepositoryProtocol (structural subtyping).
    """

    def create(self, source_uid: str, target_uid: str) -> LinkRecord:
        """Создаёт связь LINK_TO между двумя блоками."""
        with db.transaction:
            try:
                source = OrmBlock.nodes.get(uid=source_uid)
            except DoesNotExist:
                raise NotFoundError("Block", source_uid)
            try:
                target = OrmBlock.nodes.get(uid=target_uid)
            except DoesNotExist:
                raise NotFoundError("Block", target_uid)

            rel = source.target.connect(target)
            rel.save()
            return LinkRecord(uid=rel.uid, source_id=source_uid, target_id=target_uid)

    def delete_by_id(self, link_uid: str) -> None:
        """Удаляет связь по её UID."""
        with db.transaction:
            result, _ = db.cypher_query(
                "MATCH ()-[r:LINK_TO {uid: $uid}]->() DELETE r RETURN count(r) as cnt",
                {"uid": link_uid},
            )
            deleted = result[0][0] if result else 0
            if deleted == 0:
                raise NotFoundError("Link", link_uid)

    def delete_all_for_block(self, block_uid: str) -> None:
        """Удаляет все входящие и исходящие связи блока."""
        with db.transaction:
            db.cypher_query(
                "MATCH (b:Block {uid: $uid})-[r:LINK_TO]->() DELETE r",
                {"uid": block_uid},
            )
            db.cypher_query(
                "MATCH ()-[r:LINK_TO]->(b:Block {uid: $uid}) DELETE r",
                {"uid": block_uid},
            )

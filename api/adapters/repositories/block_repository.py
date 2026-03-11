"""
Layer: Interface Adapters — Repository
Package: adapters.repositories.block_repository
Responsibility: neomodel-реализация BlockRepositoryProtocol.

Принадлежит слою Interface Adapters, потому что транслирует между
доменным языком (domain.models.block) и ORM-деталями (neomodel).
Знает о neomodel, но application-слой — нет.

Удовлетворяет BlockRepositoryProtocol (application/ports/repositories.py)
без явного наследования (structural subtyping).

Allowed imports: neomodel, infrastructure.neo4j.orm_models, domain.models.*, domain.exceptions
Forbidden imports: fastapi, web, grpc, aioboto3
"""
from __future__ import annotations

import logging
from typing import Optional, List, Tuple

from neomodel import db, DoesNotExist

from infrastructure.neo4j.orm_models import Block as OrmBlock, LinkRel
from domain.models.block import Block, LinkRecord
from domain.exceptions import NotFoundError

logger = logging.getLogger(__name__)


def _orm_to_domain(orm_block: OrmBlock) -> Block:
    """Транслирует ORM-объект Block в доменный dataclass."""
    return Block(
        uid=orm_block.uid,
        content=orm_block.content,
        layer=orm_block.layer or 0,
        level=orm_block.level or 0,
        sublevel_id=orm_block.sublevel_id if orm_block.sublevel_id is not None else -1,
        physical_scale=getattr(orm_block, "physical_scale", 0) or 0,
        is_pinned=orm_block.is_pinned or False,
        data=orm_block.data,
    )


class BlockRepository:
    """
    neomodel-реализация репозитория блоков.
    Удовлетворяет BlockRepositoryProtocol (structural subtyping).
    """

    def get_by_id(self, uid: str) -> Optional[Block]:
        try:
            orm_block = OrmBlock.nodes.get(uid=uid)
            return _orm_to_domain(orm_block)
        except DoesNotExist:
            return None

    def get_all(self) -> List[Block]:
        return [_orm_to_domain(b) for b in OrmBlock.nodes.all()]

    def get_all_with_links(self) -> Tuple[List[Block], List[LinkRecord]]:
        """Возвращает все блоки и связи одним Cypher-запросом."""
        blocks_query = (
            "MATCH (b:Block) RETURN b.uid as id, b.content as content, "
            "b.layer as layer, b.level as level, b.is_pinned as is_pinned, "
            "b.physical_scale as physical_scale"
        )
        links_query = (
            "MATCH (b1:Block)-[r:LINK_TO]->(b2:Block) "
            "RETURN r.uid as id, b1.uid as source_id, b2.uid as target_id"
        )
        blocks_result, _ = db.cypher_query(blocks_query)
        links_result, _ = db.cypher_query(links_query)

        blocks = [
            Block(
                uid=str(r[0]),
                content=str(r[1] or ""),
                layer=int(r[2] or 0),
                level=int(r[3] or 0),
                is_pinned=bool(r[4]) if r[4] is not None else False,
                physical_scale=int(r[5] or 0) if r[5] is not None else 0,
            )
            for r in blocks_result
        ]
        links = [
            LinkRecord(
                uid=str(r[0]) if r[0] else "",
                source_id=str(r[1]),
                target_id=str(r[2]),
            )
            for r in links_result
        ]
        return blocks, links

    def get_outgoing_neighbor_ids(self, uid: str) -> List[str]:
        """Возвращает ID всех прямых исходящих соседей для проверки ацикличности."""
        query = (
            "MATCH (b:Block {uid: $uid})-[:LINK_TO]->(n:Block) RETURN n.uid as uid"
        )
        result, _ = db.cypher_query(query, {"uid": uid})
        return [str(r[0]) for r in result]

    def save(self, block: Block) -> Block:
        """Создаёт или обновляет блок. Если uid пустой — создаёт новый."""
        with db.transaction:
            try:
                orm_block = OrmBlock.nodes.get(uid=block.uid) if block.uid else None
            except DoesNotExist:
                orm_block = None

            if orm_block is None:
                orm_block = OrmBlock(
                    content=block.content,
                    layer=block.layer,
                    level=block.level,
                    sublevel_id=block.sublevel_id,
                    physical_scale=block.physical_scale,
                    is_pinned=block.is_pinned,
                    data=block.data,
                )
            else:
                orm_block.content = block.content
                orm_block.layer = block.layer
                orm_block.level = block.level
                orm_block.sublevel_id = block.sublevel_id
                orm_block.physical_scale = block.physical_scale
                orm_block.is_pinned = block.is_pinned
                orm_block.data = block.data

            orm_block.save()
            orm_block.refresh()
            return _orm_to_domain(orm_block)

    def delete(self, uid: str) -> None:
        """Удаляет блок и все его связи."""
        with db.transaction:
            try:
                orm_block = OrmBlock.nodes.get(uid=uid)
            except DoesNotExist:
                raise NotFoundError("Block", uid)

            db.cypher_query(
                "MATCH (b:Block {uid: $uid})-[r:LINK_TO]->() DELETE r",
                {"uid": uid},
            )
            db.cypher_query(
                "MATCH ()-[r:LINK_TO]->(b:Block {uid: $uid}) DELETE r",
                {"uid": uid},
            )
            orm_block.delete()

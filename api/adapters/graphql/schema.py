"""
Layer: Interface Adapters — GraphQL
Package: adapters.graphql.schema
Responsibility: Strawberry GraphQL schema — Query и Mutation, вызывающие use cases.

Принадлежит слою Interface Adapters. GraphQL-резолверы используют те же use cases,
что и REST-роутеры в web/routers/. Нет дублирования бизнес-логики.

Ключевое изменение по сравнению с src/schema.py:
  - Мутации create_link и delete_link теперь вызывают use cases (create_link, delete_link),
    а не напрямую Block.link_to() / Block.unlink() из ORM-модели.
  - Запросы используют BlockRepository вместо прямого Block.nodes.*

Allowed imports: strawberry, adapters.graphql.types, application.*, adapters.repositories.*
Forbidden imports: neomodel (напрямую в резолверах), fastapi, web
"""
import strawberry
from typing import List, Optional

from adapters.graphql.types import (
    UserType, BlockType, TagType, LinkMetadataType,
    CreateBlockInput, CreateLinkInput, CreateTagInput,
)
from adapters.repositories.block_repository import BlockRepository
from adapters.repositories.link_repository import LinkRepository
from application.blocks.create_block import create_block
from application.links.create_link import create_link
from application.links.delete_link import delete_link
from domain.exceptions import NotFoundError, CyclicGraphError
from infrastructure.grpc_clients.auth_grpc_client import auth_client


def _get_block_repo() -> BlockRepository:
    return BlockRepository()


def _get_link_repo() -> LinkRepository:
    return LinkRepository()


@strawberry.type
class Query:
    @strawberry.field
    def users(self) -> List[UserType]:
        result = auth_client.list_users()
        if not result.get("success"):
            return []
        return [
            UserType(id=u["uid"], login=u["login"], nickname=u["nickname"])
            for u in result.get("users", [])
        ]

    @strawberry.field
    def user(self, user_id: str) -> Optional[UserType]:
        from neomodel import DoesNotExist
        # Пробуем через auth microservice
        result = auth_client.get_user_by_id(user_id)
        if result.get("success") and result.get("user"):
            u = result["user"]
            return UserType(id=u["uid"], login=u["login"], nickname=u["nickname"])
        return None

    @strawberry.field
    def blocks(self) -> List[BlockType]:
        repo = _get_block_repo()
        return [
            BlockType(id=b.uid, content=b.content, layer=b.layer, level=b.level)
            for b in repo.get_all()
        ]

    @strawberry.field
    def block(self, block_id: str) -> Optional[BlockType]:
        repo = _get_block_repo()
        b = repo.get_by_id(block_id)
        if b is None:
            return None
        return BlockType(id=b.uid, content=b.content, layer=b.layer, level=b.level)

    @strawberry.field
    def blocks_by_layer(self, layer: int) -> List[BlockType]:
        from infrastructure.neo4j.orm_models import Block as OrmBlock
        return [
            BlockType(id=b.uid, content=b.content, layer=b.layer, level=b.level)
            for b in OrmBlock.nodes.filter(layer=layer)
        ]

    @strawberry.field
    def tags(self) -> List[TagType]:
        from infrastructure.neo4j.orm_models import Tag
        return [TagType(text=t.text) for t in Tag.nodes.all()]

    @strawberry.field
    def links(self) -> List[LinkMetadataType]:
        from infrastructure.neo4j.orm_models import LinkMetadata
        return [
            LinkMetadataType(id=lm.uid, source_id=lm.source_id or "", target_id=lm.target_id or "")
            for lm in LinkMetadata.nodes.all()
        ]


@strawberry.type
class Mutation:
    @strawberry.field
    def create_block(self, input: CreateBlockInput) -> BlockType:
        repo = _get_block_repo()
        b = create_block(repo=repo, content=input.content, layer=input.layer)
        return BlockType(id=b.uid, content=b.content, layer=b.layer, level=b.level)

    @strawberry.field
    def create_link(self, input: CreateLinkInput) -> LinkMetadataType:
        """Создаёт связь с проверкой ацикличности через use case."""
        block_repo = _get_block_repo()
        link_repo = _get_link_repo()
        try:
            link = create_link(
                block_repo=block_repo,
                link_repo=link_repo,
                source_id=input.source_id,
                target_id=input.target_id,
            )
            return LinkMetadataType(id=link.uid, source_id=link.source_id, target_id=link.target_id)
        except (NotFoundError, CyclicGraphError) as e:
            raise ValueError(str(e))

    @strawberry.field
    def create_tag(self, input: CreateTagInput) -> TagType:
        from infrastructure.neo4j.orm_models import Tag
        tag, _ = Tag.get_or_create({"text": input.text})
        return TagType(text=tag.text)

    @strawberry.field
    def add_tag_to_block(self, block_id: str, tag_text: str) -> BlockType:
        from infrastructure.neo4j.orm_models import Tag, Block as OrmBlock
        from neomodel import DoesNotExist
        try:
            block = OrmBlock.nodes.get(uid=block_id)
        except DoesNotExist:
            raise ValueError(f"Block {block_id} not found")
        tag, _ = Tag.get_or_create({"text": tag_text})
        tag.block.connect(block)
        return BlockType(id=block.uid, content=block.content, layer=block.layer, level=block.level)

    @strawberry.field
    def delete_link(self, source_id: str, target_id: str) -> bool:
        """Удаляет связь по source/target через Cypher — use case delete_link использует uid."""
        from neomodel import db
        result, _ = db.cypher_query(
            "MATCH (s:Block {uid: $src})-[r:LINK_TO]->(t:Block {uid: $tgt}) DELETE r RETURN count(r)",
            {"src": source_id, "tgt": target_id},
        )
        return (result[0][0] if result else 0) > 0


schema = strawberry.Schema(query=Query, mutation=Mutation)

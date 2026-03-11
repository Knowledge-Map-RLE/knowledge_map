"""
Layer: Interface Adapters — GraphQL
Package: adapters.graphql.types
Responsibility: Strawberry GraphQL type definitions.

Принадлежит слою Interface Adapters — транслирует доменные модели в GraphQL-типы.

Allowed imports: strawberry, typing
Forbidden imports: neomodel, fastapi, domain, application (напрямую)
"""
import strawberry
from typing import List, Optional


@strawberry.type
class UserType:
    id: str
    login: str
    nickname: str


@strawberry.type
class TagType:
    text: str


@strawberry.type
class LinkMetadataType:
    id: str
    source_id: str
    target_id: str


@strawberry.type
class BlockType:
    id: str
    content: str
    layer: int
    level: int
    tags: List[TagType] = strawberry.field(default_factory=list)


# Input types
@strawberry.input
class CreateBlockInput:
    content: str
    layer: int = 0


@strawberry.input
class CreateLinkInput:
    source_id: str
    target_id: str


@strawberry.input
class CreateTagInput:
    text: str

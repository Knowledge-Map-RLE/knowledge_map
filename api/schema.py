import strawberry
from typing import List, Optional
from models import User, Block, Tag, LinkMetadata

# GraphQL Types
@strawberry.type
class UserType:
    id: str
    login: str
    nickname: str
    surname: Optional[str] = None
    given_names: Optional[str] = None

@strawberry.type
class TagType:
    text: str

@strawberry.type 
class LinkMetadataType:
    id: str
    source_id: str
    target_id: str
    created_by: UserType

@strawberry.type
class BlockType:
    id: str
    content: str
    layer: int
    level: int
    created_by: Optional[UserType] = None
    tags: List[TagType] = strawberry.field(default_factory=list)

# Input Types
@strawberry.input
class CreateUserInput:
    login: str
    password: str
    nickname: str
    surname: Optional[str] = None
    given_names: Optional[str] = None

@strawberry.input
class CreateBlockInput:
    content: str
    layer: int
    level: int
    user_id: str

@strawberry.input
class CreateLinkInput:
    source_id: str
    target_id: str
    user_id: str

@strawberry.input
class CreateTagInput:
    text: str

# Resolvers для преобразования моделей в GraphQL типы
def resolve_user(user: User) -> UserType:
    return UserType(
        id=getattr(user, 'element_id'),  # ✅ Используем getattr для безопасного доступа к нашему UUID полю
        login=user.login,
        nickname=user.nickname,
        surname=user.surname,
        given_names=user.given_names
    )

def resolve_block(block: Block) -> BlockType:
    created_by = None
    if block.created_by.single():
        created_by = resolve_user(block.created_by.single())
    
    tags = [TagType(text=tag.text) for tag in block.get_tags()]
    
    return BlockType(
        id=getattr(block, 'element_id'),  # ✅ Используем getattr для безопасного доступа к нашему UUID полю
        content=block.content,
        layer=block.layer,
        level=block.level,
        created_by=created_by,
        tags=tags
    )

def resolve_tag(tag: Tag) -> TagType:
    return TagType(text=tag.text)

def resolve_link_metadata(link: LinkMetadata) -> LinkMetadataType:
    created_by = resolve_user(link.created_by.single())
    return LinkMetadataType(
        id=getattr(link, 'element_id'),  # ✅ Используем getattr для безопасного доступа к нашему UUID полю
        source_id=link.source_id,
        target_id=link.target_id,
        created_by=created_by
    )

# Queries
@strawberry.type
class Query:
    @strawberry.field
    def users(self) -> List[UserType]:
        """Получить всех пользователей"""
        return [resolve_user(user) for user in User.nodes.all()]
    
    @strawberry.field
    def user(self, user_id: str) -> Optional[UserType]:
        """Получить пользователя по ID"""
        try:
            user = User.nodes.get(id=user_id)
            return resolve_user(user)
        except User.DoesNotExist:
            return None
    
    @strawberry.field
    def blocks(self) -> List[BlockType]:
        """Получить все блоки"""
        return [resolve_block(block) for block in Block.nodes.all()]
    
    @strawberry.field
    def block(self, block_id: str) -> Optional[BlockType]:
        """Получить блок по ID"""
        try:
            block = Block.nodes.get(id=block_id)
            return resolve_block(block)
        except Block.DoesNotExist:
            return None
    
    @strawberry.field
    def blocks_by_layer(self, layer: int) -> List[BlockType]:
        """Получить блоки по слою"""
        blocks = Block.nodes.filter(layer=layer)
        return [resolve_block(block) for block in blocks]
    
    @strawberry.field
    def tags(self) -> List[TagType]:
        """Получить все теги"""
        return [resolve_tag(tag) for tag in Tag.nodes.all()]
    
    @strawberry.field
    def links(self) -> List[LinkMetadataType]:
        """Получить все связи"""
        return [resolve_link_metadata(link) for link in LinkMetadata.nodes.all()]

# Mutations
@strawberry.type
class Mutation:
    @strawberry.field
    def create_user(self, input: CreateUserInput) -> UserType:
        """Создать пользователя"""
        user = User(
            login=input.login,
            password=input.password,  # В реальном приложении нужно хешировать!
            nickname=input.nickname,
            surname=input.surname,
            given_names=input.given_names
        ).save()
        return resolve_user(user)
    
    @strawberry.field
    def create_block(self, input: CreateBlockInput) -> BlockType:
        """Создать блок"""
        try:
            user = User.nodes.get(id=input.user_id)
            block = Block(
                content=input.content,
                layer=input.layer,
                level=input.level
            ).save()
            block.created_by.connect(user)
            return resolve_block(block)
        except User.DoesNotExist:
            raise ValueError(f"Пользователь с ID {input.user_id} не найден")
    
    @strawberry.field
    def create_link(self, input: CreateLinkInput) -> LinkMetadataType:
        """Создать связь между блоками"""
        try:
            source = Block.nodes.get(id=input.source_id)
            target = Block.nodes.get(id=input.target_id)
            user = User.nodes.get(id=input.user_id)
            
            link_metadata = source.link_to(target, user)
            return resolve_link_metadata(link_metadata)
            
        except Block.DoesNotExist:
            raise ValueError("Один из блоков не найден")
        except User.DoesNotExist:
            raise ValueError(f"Пользователь с ID {input.user_id} не найден")
        except ValueError as e:
            raise ValueError(str(e))  # Ошибка ацикличности
    
    @strawberry.field
    def create_tag(self, input: CreateTagInput) -> TagType:
        """Создать тег"""
        tag = Tag(text=input.text).save()
        return resolve_tag(tag)
    
    @strawberry.field
    def add_tag_to_block(self, block_id: str, tag_text: str) -> BlockType:
        """Добавить тег к блоку"""
        try:
            block = Block.nodes.get(id=block_id)
            tag, created = Tag.get_or_create({'text': tag_text})
            tag.block.connect(block)
            return resolve_block(block)
        except Block.DoesNotExist:
            raise ValueError(f"Блок с ID {block_id} не найден")
    
    @strawberry.field
    def delete_link(self, source_id: str, target_id: str) -> bool:
        """Удалить связь между блоками"""
        try:
            source = Block.nodes.get(id=source_id)
            target = Block.nodes.get(id=target_id)
            source.unlink(target)
            return True
        except Block.DoesNotExist:
            return False

# Создаем схему
schema = strawberry.Schema(query=Query, mutation=Mutation)
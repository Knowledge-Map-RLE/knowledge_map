"""
Layer: Application (Use Cases) — Ports
Package: application.ports.repositories
Responsibility: Protocol-определения для операций с хранилищем (driven ports).

Принадлежит слою Application. Определяет, что нужно бизнес-логике от уровня
персистентности, не зная о деталях реализации.
Реализации находятся в adapters/repositories/.

Правило зависимостей: этот файл смотрит внутрь — импортирует только из domain/.
Слои adapters и infrastructure импортируют ЭТИ Protocol-ы, не наоборот.
Structural subtyping (typing.Protocol) — реализации не обязаны импортировать Protocol.

Allowed imports: typing, domain.models.*, domain.exceptions
Forbidden imports: neomodel, aioboto3, grpc, fastapi, adapters, infrastructure, web
"""
from __future__ import annotations

from typing import Protocol, Optional, List, Tuple

from domain.models.block import Block, LinkRecord
from domain.models.document import PDFDocument
from domain.models.annotation import MarkdownAnnotation, AnnotationRelation
from domain.models.user import User


class BlockRepositoryProtocol(Protocol):
    """Операции с блоками графа знаний."""

    def get_by_id(self, uid: str) -> Optional[Block]: ...

    def get_all(self) -> List[Block]: ...

    def get_all_with_links(self) -> Tuple[List[Block], List[LinkRecord]]: ...

    def get_outgoing_neighbor_ids(self, uid: str) -> List[str]:
        """Возвращает ID всех прямых исходящих соседей (для проверки ацикличности)."""
        ...

    def save(self, block: Block) -> Block: ...

    def delete(self, uid: str) -> None: ...


class LinkRepositoryProtocol(Protocol):
    """Операции со связями между блоками."""

    def create(self, source_uid: str, target_uid: str) -> LinkRecord: ...

    def delete_by_id(self, link_uid: str) -> None: ...

    def delete_all_for_block(self, block_uid: str) -> None: ...


class DocumentRepositoryProtocol(Protocol):
    """Операции с PDF-документами."""

    def get_by_id(self, uid: str) -> Optional[PDFDocument]: ...

    def get_by_md5(self, md5_hash: str) -> Optional[PDFDocument]: ...

    def save(self, doc: PDFDocument) -> PDFDocument: ...

    def delete(self, uid: str) -> None: ...

    def list_all(self) -> List[PDFDocument]: ...


class AnnotationRepositoryProtocol(Protocol):
    """Операции с Markdown-аннотациями."""

    def create(self, annotation: MarkdownAnnotation, doc_id: str) -> MarkdownAnnotation: ...

    def get_by_id(self, uid: str) -> Optional[MarkdownAnnotation]: ...

    def get_by_document(
        self,
        doc_id: str,
        skip: int = 0,
        limit: Optional[int] = None,
        annotation_types: Optional[List[str]] = None,
        source: Optional[str] = None,
    ) -> Tuple[List[MarkdownAnnotation], int]:
        """Возвращает (список аннотаций, общее кол-во)."""
        ...

    def save(self, annotation: MarkdownAnnotation) -> MarkdownAnnotation: ...

    def delete(self, uid: str) -> None: ...

    def delete_all_for_document(self, doc_id: str) -> int:
        """Удаляет все аннотации документа, возвращает количество."""
        ...

    def count_for_document(self, doc_id: str) -> int: ...

    def create_relation(
        self,
        source_uid: str,
        target_uid: str,
        relation_type: str,
        metadata: Optional[dict] = None,
    ) -> AnnotationRelation: ...

    def delete_relation(self, source_uid: str, target_uid: str) -> None: ...

    def get_relations_for_document(self, doc_id: str) -> List[AnnotationRelation]: ...

    def batch_update_offsets(
        self, updates: List[dict]
    ) -> Tuple[int, List[str]]:
        """Массовое обновление offsets. Возвращает (updated_count, errors)."""
        ...


class UserRepositoryProtocol(Protocol):
    """Операции с пользователями."""

    def get_by_id(self, uid: str) -> Optional[User]: ...

    def get_or_create_test_user(self) -> User: ...


class LinguisticPatternRepositoryProtocol(Protocol):
    """Операции с лингвистическими паттернами."""

    def save_patterns(self, patterns: List[dict], doc_id: str) -> int:
        """Сохраняет паттерны, возвращает количество сохранённых."""
        ...

    def get_for_document(
        self,
        doc_id: str,
        annotation_types: Optional[List[str]] = None,
        min_frequency: int = 1,
    ) -> List[dict]:
        """Возвращает паттерны документа с фильтрацией по типу аннотации."""
        ...

    def delete_for_document(self, doc_id: str) -> int:
        """Удаляет все паттерны документа, возвращает количество."""
        ...

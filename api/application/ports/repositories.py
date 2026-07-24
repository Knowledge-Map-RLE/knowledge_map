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
from domain.models.document import Document
from domain.models.annotation import MarkdownAnnotation, AnnotationRelation


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
    """Операции с документами."""

    def get_by_id(self, uid: str) -> Optional[Document]: ...

    def get_by_md5(self, md5_hash: str) -> Optional[Document]: ...

    def save(self, doc: Document) -> Document: ...

    def delete(self, uid: str) -> None: ...

    def list_all(
        self,
        skip: int = 0,
        limit: Optional[int] = None,
    ) -> List[Document]: ...

    def count_all(self) -> int:
        """Общее количество документов — для пагинации."""
        ...

    def search(
        self,
        q: str,
        skip: int = 0,
        limit: int = 100,
    ) -> Tuple[List[Document], int]:
        """Нечёткий поиск по названию. Возвращает (документы, всего_найдено)."""
        ...

    
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


class LinguisticPatternRepositoryProtocol(Protocol):
    """Операции с лингвистическими паттернами."""

    def save_patterns(self, patterns: List[dict], doc_id: str) -> int: ...

    def get_for_document(
        self,
        doc_id: str,
        annotation_types: Optional[List[str]] = None,
        min_frequency: int = 1,
    ) -> List[dict]: ...

    def delete_for_document(self, doc_id: str) -> int: ...


class PatternGraphRepositoryProtocol(Protocol):
    """Операции для получения графа Action + LexicalUnit с рёбрами LEADS_TO, DEPENDS_ON, PART_OF."""

    def get_document_linguistic_graph(self, doc_id: str) -> Tuple[List[dict], List[dict]]:
        """Возвращает (nodes, edges) лингвистического графа одного документа.

        Nodes: Action и LexicalUnit с их атрибутами.
        Edges: LEADS_TO (Action→Action), DEPENDS_ON (LexicalUnit→LexicalUnit), PART_OF (LexicalUnit→Action).
        """
        ...

    def get_global_linguistic_graph(self) -> Tuple[List[dict], List[dict]]:
        """Возвращает (nodes, edges) объединённого лингвистического графа всех документов.

        Те же типы узлов и рёбер, но без фильтрации по doc_id.
        """
        ...




class ActionRepositoryProtocol(Protocol):
    """Операции с узлами Action и рёбрами LEADS_TO."""

    def save_actions(self, actions: List[dict], doc_id: str) -> int:
        """Сохраняет список action-словарей, возвращает количество."""
        ...

    def save_leads_to(self, action_edges: List[dict], doc_id: str) -> int:
        """Сохраняет рёбра Action→Action, возвращает количество."""
        ...

    def get_for_document(self, doc_id: str) -> List[dict]:
        """Возвращает все Action узлы документа."""
        ...

    def get_pending_for_document(self, doc_id: str) -> List[dict]:
        """Возвращает все pending рёбра LEADS_TO документа (Action→Action)."""
        ...

    def get_neighbor_ids(self, uid: str) -> List[str]:
        """Возвращает ID прямых исходящих соседей (для проверки ацикличности)."""
        ...

    def update_edge_status(self, src_uid: str, tgt_uid: str, relation_subtype: str, status: str) -> None:
        """Обновляет статус ребра."""
        ...

    def delete_for_document(self, doc_id: str) -> int:
        """Удаляет все Action узлы документа (DETACH DELETE), возвращает количество."""
        ...

    def backfill_norm_keys(self) -> int:
        """Проставляет norm_key для Action-нод без него. Возвращает количество обновлённых."""
        ...

    def get_aggregated_graph(self) -> Tuple[List[dict], List[dict]]:
        """Возвращает агрегированный граф: (ноды-представители по norm_key, рёбра между ними)."""
        ...

    def search_lexical_units(
        self,
        lemma: Optional[str] = None,
        pos: Optional[str] = None,
        dep: Optional[str] = None,
        doc_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[dict]:
        """Поиск LexicalUnit по атрибутам."""
        ...

    def find_dependency_patterns(self, doc_id: Optional[str] = None) -> List[dict]:
        """Находит частотные пары head→dependent через DEPENDS_ON."""
        ...

    def find_shared_patterns(self, min_docs: int = 2) -> List[dict]:
        """Находит паттерны, повторяющиеся в разных документах."""
        ...

    def compare_actions(self, uid1: str, uid2: str) -> dict:
        """Сравнивает лингвистическую структуру двух Actions."""
        ...

    def get_lexical_graph_stats(self) -> dict:
        """Возвращает статистику лингвистического графа."""
        ...

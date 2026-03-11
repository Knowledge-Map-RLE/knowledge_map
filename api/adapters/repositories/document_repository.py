"""
Layer: Interface Adapters — Repository
Package: adapters.repositories.document_repository
Responsibility: neomodel-реализация DocumentRepositoryProtocol.

Allowed imports: neomodel, infrastructure.neo4j.orm_models, domain.models.document, domain.exceptions
Forbidden imports: fastapi, web, grpc, aioboto3
"""
from __future__ import annotations

import logging
from typing import Optional, List

from neomodel import DoesNotExist

from infrastructure.neo4j.orm_models import PDFDocument as OrmDocument
from domain.models.document import PDFDocument
from domain.exceptions import NotFoundError

logger = logging.getLogger(__name__)


def _orm_to_domain(orm_doc: OrmDocument) -> PDFDocument:
    """Транслирует ORM-объект PDFDocument в доменный dataclass."""
    return PDFDocument(
        uid=orm_doc.uid,
        original_filename=orm_doc.original_filename,
        md5_hash=orm_doc.md5_hash,
        s3_bucket=orm_doc.s3_bucket or "knowledge-map-data",
        s3_key=orm_doc.s3_key,
        file_size=orm_doc.file_size,
        upload_date=orm_doc.upload_date,
        title=orm_doc.title,
        authors=orm_doc.authors,
        abstract=orm_doc.abstract,
        keywords=orm_doc.keywords,
        publication_date=orm_doc.publication_date,
        journal=orm_doc.journal,
        doi=orm_doc.doi,
        docling_raw_md_s3_key=orm_doc.docling_raw_md_s3_key,
        formatted_md_s3_key=orm_doc.formatted_md_s3_key,
        user_md_s3_key=orm_doc.user_md_s3_key,
        source=orm_doc.source or "upload",
        pubmed_id=orm_doc.pubmed_id,
        pmc_id=orm_doc.pmc_id,
        is_open_access=orm_doc.is_open_access or False,
        is_processed=orm_doc.is_processed or False,
        processing_status=orm_doc.processing_status or "uploaded",
        error_message=orm_doc.error_message,
    )


def _domain_to_orm(doc: PDFDocument, orm_doc: Optional[OrmDocument] = None) -> OrmDocument:
    """Заполняет ORM-объект из доменного dataclass."""
    if orm_doc is None:
        orm_doc = OrmDocument(
            original_filename=doc.original_filename,
            md5_hash=doc.md5_hash,
            s3_bucket=doc.s3_bucket,
            s3_key=doc.s3_key,
        )
    orm_doc.original_filename = doc.original_filename
    orm_doc.md5_hash = doc.md5_hash
    orm_doc.s3_bucket = doc.s3_bucket
    orm_doc.s3_key = doc.s3_key
    orm_doc.file_size = doc.file_size
    orm_doc.title = doc.title
    orm_doc.authors = doc.authors
    orm_doc.abstract = doc.abstract
    orm_doc.keywords = doc.keywords
    orm_doc.publication_date = doc.publication_date
    orm_doc.journal = doc.journal
    orm_doc.doi = doc.doi
    orm_doc.docling_raw_md_s3_key = doc.docling_raw_md_s3_key
    orm_doc.formatted_md_s3_key = doc.formatted_md_s3_key
    orm_doc.user_md_s3_key = doc.user_md_s3_key
    orm_doc.source = doc.source
    orm_doc.pubmed_id = doc.pubmed_id
    orm_doc.pmc_id = doc.pmc_id
    orm_doc.is_open_access = doc.is_open_access
    orm_doc.is_processed = doc.is_processed
    orm_doc.processing_status = doc.processing_status
    orm_doc.error_message = doc.error_message
    return orm_doc


class DocumentRepository:
    """
    neomodel-реализация репозитория PDF-документов.
    Удовлетворяет DocumentRepositoryProtocol (structural subtyping).
    """

    def get_by_id(self, uid: str) -> Optional[PDFDocument]:
        try:
            return _orm_to_domain(OrmDocument.nodes.get(uid=uid))
        except DoesNotExist:
            return None

    def get_by_md5(self, md5_hash: str) -> Optional[PDFDocument]:
        try:
            return _orm_to_domain(OrmDocument.nodes.get(md5_hash=md5_hash))
        except DoesNotExist:
            return None

    def save(self, doc: PDFDocument) -> PDFDocument:
        try:
            orm_doc = OrmDocument.nodes.get(uid=doc.uid) if doc.uid else None
        except DoesNotExist:
            orm_doc = None

        orm_doc = _domain_to_orm(doc, orm_doc)
        orm_doc.save()
        orm_doc.refresh()
        return _orm_to_domain(orm_doc)

    def delete(self, uid: str) -> None:
        try:
            orm_doc = OrmDocument.nodes.get(uid=uid)
        except DoesNotExist:
            raise NotFoundError("PDFDocument", uid)
        orm_doc.delete()

    def list_all(self) -> List[PDFDocument]:
        return [_orm_to_domain(d) for d in OrmDocument.nodes.all()]

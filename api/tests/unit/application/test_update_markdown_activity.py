import asyncio

from domain.models.document import Document
from application.documents.update_markdown import update_markdown


class FakeDocumentRepository:
    def __init__(self):
        self.events = []
        self.document = Document(
            uid="doc-1",
            original_filename="old.md",
            md5_hash="hash-1",
            s3_bucket="bucket",
            s3_key="",
        )

    def get_by_id(self, _doc_id):
        return self.document

    def save(self, document):
        self.events.append(("save", document.uid))
        return document

    def record_user_edit(self, user_uid, doc_uid):
        self.events.append(("edit", user_uid, doc_uid))
        return True


class FakeStorage:
    async def upload_bytes(self, **_kwargs):
        return True


def test_markdown_save_records_activity_after_document_save():
    repository = FakeDocumentRepository()

    result = asyncio.run(
        update_markdown(
            document_repo=repository,
            storage=FakeStorage(),
            doc_id="doc-1",
            markdown="# New title\n\nBody",
            bucket="bucket",
            user_uid="user-1",
        )
    )

    assert result["title"] == "New title"
    assert repository.events == [("save", "doc-1"), ("edit", "user-1", "doc-1")]

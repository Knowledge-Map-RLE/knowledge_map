"""Unit-тесты безопасной подготовки миграции исходного Markdown."""

from io import BytesIO

import pytest
from botocore.exceptions import ClientError

from data_to_db.migrate_raw_markdown_storage import (
    RawMarkdownStorageMigration,
    target_key,
)


class _MemoryS3:
    def __init__(self, objects):
        self.objects = dict(objects)

    def head_object(self, Bucket, Key):
        try:
            data = self.objects[(Bucket, Key)]
        except KeyError as exc:
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject") from exc
        return {"ContentLength": len(data)}

    def get_object(self, Bucket, Key):
        return {"Body": BytesIO(self.objects[(Bucket, Key)])}

    def copy_object(self, Bucket, Key, CopySource, MetadataDirective):
        self.objects[(Bucket, Key)] = self.objects[
            (CopySource["Bucket"], CopySource["Key"])
        ]


def test_target_key_uses_neutral_filename_and_preserves_folder():
    assert target_key("documents/old-id/docling.md", "doc-42") == (
        "documents/old-id/doc-42_raw.md"
    )
    assert target_key("old.md", "doc-42") == "doc-42_raw.md"


def test_verified_copy_compares_size_and_sha256_before_repointing():
    bucket = "documents"
    old_key = "old/docling.md"
    new_key = "old/doc-42_raw.md"
    s3 = _MemoryS3({(bucket, old_key): b"valid markdown"})
    migration = RawMarkdownStorageMigration(
        driver=object(), s3_client=s3, default_bucket=bucket
    )

    migration._verified_copy(bucket, old_key, new_key)
    assert s3.objects[(bucket, new_key)] == b"valid markdown"

    s3.objects[(bucket, new_key)] = b"badid markdown"
    with pytest.raises(RuntimeError, match="Контрольные суммы"):
        migration._verified_copy(bucket, old_key, new_key)

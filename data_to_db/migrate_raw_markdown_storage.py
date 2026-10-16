"""Одноразовая миграция S3-ключей Markdown и свойства Neo4j Document."""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
from pathlib import PurePosixPath
from typing import Any, Dict, Iterable, Optional

import boto3
from botocore.exceptions import ClientError
from neo4j import GraphDatabase

logger = logging.getLogger("raw_markdown_migration")


def target_key(old_key: str, document_id: str) -> str:
    """Строит engine-neutral ключ, оставляя прежний префикс каталога."""
    parent = PurePosixPath(old_key).parent
    filename = f"{document_id}_raw.md"
    return str(parent / filename) if str(parent) != "." else filename


def sha256_object(s3_client: Any, bucket: str, key: str) -> tuple[str, int]:
    """Вычисляет SHA-256 потоково, не загружая объект целиком в память."""
    response = s3_client.get_object(Bucket=bucket, Key=key)
    body = response["Body"]
    digest = hashlib.sha256()
    size = 0
    try:
        while chunk := body.read(8 * 1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    finally:
        body.close()
    return digest.hexdigest(), size


class RawMarkdownStorageMigration:
    """Копирует, проверяет, перепривязывает и затем удаляет старые объекты."""

    def __init__(self, driver: Any, s3_client: Any, default_bucket: str) -> None:
        self.driver = driver
        self.s3 = s3_client
        self.default_bucket = default_bucket

    def _documents(self) -> Iterable[Dict[str, Any]]:
        query = """
        MATCH (d:Document)
        WHERE d.docling_raw_md_s3_key IS NOT NULL
        RETURN d.uid AS uid,
               d.docling_raw_md_s3_key AS old_key,
               coalesce(d.s3_bucket, $default_bucket) AS bucket
        ORDER BY d.uid
        """
        with self.driver.session() as session:
            return list(
                session.run(query, default_bucket=self.default_bucket).data()
            )

    def _pending_cleanup(self) -> Iterable[Dict[str, Any]]:
        query = """
        MATCH (d:Document)
        WHERE d.raw_markdown_previous_s3_key IS NOT NULL
        RETURN d.uid AS uid,
               d.raw_markdown_previous_s3_key AS old_key,
               d.raw_markdown_s3_key AS new_key,
               coalesce(d.s3_bucket, $default_bucket) AS bucket
        ORDER BY d.uid
        """
        with self.driver.session() as session:
            return list(
                session.run(query, default_bucket=self.default_bucket).data()
            )

    def _set_new_key(self, row: Dict[str, Any], new_key: str) -> None:
        old_key = row["old_key"]
        query = """
        MATCH (d:Document {uid: $uid})
        WHERE d.docling_raw_md_s3_key = $old_key
        SET d.raw_markdown_s3_key = $new_key
        REMOVE d.docling_raw_md_s3_key
        """
        params = {"uid": row["uid"], "old_key": old_key, "new_key": new_key}
        if old_key != new_key:
            query = """
            MATCH (d:Document {uid: $uid})
            WHERE d.docling_raw_md_s3_key = $old_key
            SET d.raw_markdown_s3_key = $new_key,
                d.raw_markdown_previous_s3_key = $old_key
            REMOVE d.docling_raw_md_s3_key
            """
        with self.driver.session() as session:
            result = session.run(query, **params)
            summary = result.consume()
            if summary.counters.properties_set == 0:
                raise RuntimeError(
                    f"Neo4j не обновил ссылку документа {row['uid']}"
                )

    def _clear_previous_key(self, uid: str) -> None:
        with self.driver.session() as session:
            session.run(
                "MATCH (d:Document {uid: $uid}) "
                "REMOVE d.raw_markdown_previous_s3_key",
                uid=uid,
            ).consume()

    def _verified_copy(self, bucket: str, old_key: str, new_key: str) -> None:
        old_head = self.s3.head_object(Bucket=bucket, Key=old_key)
        try:
            new_head = self.s3.head_object(Bucket=bucket, Key=new_key)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code not in {"404", "NoSuchKey", "NotFound"}:
                raise
            self.s3.copy_object(
                Bucket=bucket,
                Key=new_key,
                CopySource={"Bucket": bucket, "Key": old_key},
                MetadataDirective="COPY",
            )
            new_head = self.s3.head_object(Bucket=bucket, Key=new_key)

        if old_head.get("ContentLength") != new_head.get("ContentLength"):
            raise RuntimeError(f"Размеры S3-объектов различаются: {old_key} → {new_key}")
        old_hash, old_size = sha256_object(self.s3, bucket, old_key)
        new_hash, new_size = sha256_object(self.s3, bucket, new_key)
        if old_size != new_size or old_hash != new_hash:
            raise RuntimeError(f"Контрольные суммы S3-объектов различаются: {old_key} → {new_key}")

    def _remove_previous_object(self, row: Dict[str, Any]) -> None:
        old_key = row["old_key"]
        new_key = row.get("new_key")
        bucket = row["bucket"]
        if old_key != new_key:
            try:
                self.s3.head_object(Bucket=bucket, Key=old_key)
            except ClientError as exc:
                code = exc.response.get("Error", {}).get("Code")
                if code not in {"404", "NoSuchKey", "NotFound"}:
                    raise
                # Удаление могло завершиться до сбоя, а маркер — остаться.
                # В этом случае достаточно подтвердить наличие нового объекта.
                self.s3.head_object(Bucket=bucket, Key=new_key)
            else:
                self._verified_copy(bucket, old_key, new_key)
                self.s3.delete_object(Bucket=bucket, Key=old_key)
        self._clear_previous_key(row["uid"])

    def run(self, dry_run: bool = True) -> Dict[str, int]:
        documents = list(self._documents())
        pending = list(self._pending_cleanup())
        expected_keys = {
            row["uid"]: target_key(row["old_key"], row["uid"])
            for row in documents
        }
        expected_keys.update(
            {row["uid"]: row["new_key"] for row in pending}
        )
        logger.info(
            "План миграции: документов=%s, незавершённая очистка=%s, dry_run=%s",
            len(documents),
            len(pending),
            dry_run,
        )
        if dry_run:
            for row in documents:
                logger.info(
                    "Будет перенесён %s: s3://%s/%s → s3://%s/%s",
                    row["uid"],
                    row["bucket"],
                    row["old_key"],
                    row["bucket"],
                    target_key(row["old_key"], row["uid"]),
                )
            return {"documents": len(documents), "pending_cleanup": len(pending)}

        migrated = 0
        for row in documents:
            old_key = row["old_key"]
            new_key = target_key(old_key, row["uid"])
            self._verified_copy(row["bucket"], old_key, new_key)
            self._set_new_key(row, new_key)
            if old_key != new_key:
                self._remove_previous_object(
                    {**row, "old_key": old_key, "new_key": new_key}
                )
            migrated += 1
            logger.info("Перенесён Markdown документа %s", row["uid"])

        # Повторный запуск завершает уборку после сбоя между перепривязкой и удалением.
        for row in pending:
            self._remove_previous_object(row)

        with self.driver.session() as session:
            remaining = session.run(
                "MATCH (d:Document) "
                "WHERE d.docling_raw_md_s3_key IS NOT NULL "
                "OR d.raw_markdown_previous_s3_key IS NOT NULL "
                "RETURN count(d) AS count"
            ).single()["count"]
            migrated_rows = session.run(
                "MATCH (d:Document) WHERE d.uid IN $uids "
                "RETURN d.uid AS uid, d.raw_markdown_s3_key AS new_key",
                uids=list(expected_keys),
            ).data()
        if remaining:
            raise RuntimeError(
                f"Миграция оставила {remaining} документов с прежними ссылками"
            )
        actual_keys = {row["uid"]: row["new_key"] for row in migrated_rows}
        if actual_keys != expected_keys:
            raise RuntimeError(
                "Число документов или целевые S3-ссылки после миграции не совпали: "
                f"ожидалось {len(expected_keys)}, найдено {len(actual_keys)}"
            )
        return {
            "migrated": migrated,
            "cleaned_up": len(pending),
            "remaining": 0,
            "verified_documents": len(actual_keys),
        }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Переименование S3-ключей исходного Markdown и свойства Neo4j"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Выполнить копирование, перепривязку и удаление старых объектов",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    uri = os.environ.get("NEO4J_URI")
    username = os.environ.get("NEO4J_USERNAME") or os.environ.get("NEO4J_USER")
    password = os.environ.get("NEO4J_PASSWORD")
    if not uri or not username or not password:
        parser.error("Нужны NEO4J_URI, NEO4J_USERNAME и NEO4J_PASSWORD")

    bucket = os.environ.get("S3_BUCKET_NAME", "knowledge-map-data")
    s3_client = boto3.client(
        "s3",
        endpoint_url=os.environ.get("S3_ENDPOINT_URL"),
        aws_access_key_id=os.environ.get("S3_ACCESS_KEY"),
        aws_secret_access_key=os.environ.get("S3_SECRET_KEY"),
        region_name=os.environ.get("S3_REGION", "us-east-1"),
    )
    driver = GraphDatabase.driver(uri, auth=(username, password))
    try:
        migration = RawMarkdownStorageMigration(driver, s3_client, bucket)
        result = migration.run(dry_run=not args.apply)
        logger.info("Итог миграции: %s", result)
    finally:
        driver.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

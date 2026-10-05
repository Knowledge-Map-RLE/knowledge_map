"""Чтение полного сохранённого текста статьи без альтернативных источников."""
from __future__ import annotations

import asyncio
from botocore.exceptions import ClientError
from domain.article_maps import ArticleMapError, ArticleMapAccessDenied, require


class StoredArticleMapSource:
    def __init__(self, repository, storage, bucket: str):
        self.repository, self.storage, self.bucket = repository, storage, bucket

    async def _location(self, article_id: str, user_uid: str):
        await asyncio.to_thread(self.repository.authorize, article_id, user_uid)
        def read_metadata():
            with self.repository.driver.session() as session:
                return session.run("""MATCH (d:Document {uid:$id,created_by_uid:$user})
                  RETURN d.user_md_s3_key AS user_key,d.formatted_md_s3_key AS formatted_key,
                         d.docling_raw_md_s3_key AS raw_key,d.s3_bucket AS bucket""", id=article_id, user=user_uid).single()
        row = await asyncio.to_thread(read_metadata)
        if row is None:
            raise ArticleMapAccessDenied("Article access denied")
        # Это штатный выбор сохранённой редакции; отсутствующий объект не заменяется другим.
        key = row["user_key"] or row["formatted_key"] or row["raw_key"]
        bucket = row["bucket"] or self.bucket
        return bucket, key

    async def available(self, article_id: str, user_uid: str) -> bool:
        bucket, key = await self._location(article_id, user_uid)
        return bool(key) and await self._exists(bucket, key)

    async def _exists(self, bucket, key):
        try:
            async with self.storage.client_context() as client:
                await client.head_object(Bucket=bucket, Key=key)
            return True
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise ArticleMapError("Saved article storage request failed") from exc

    async def read_text(self, article_id: str, user_uid: str) -> str:
        bucket, key = await self._location(article_id, user_uid)
        require(bool(key), "Article has no saved full text")
        if not await self._exists(bucket, key):
            raise ArticleMapError("Saved article text object is missing")
        text = await self.storage.download_text(bucket, key)
        require(isinstance(text, str) and bool(text.strip()), "Saved article full text is empty")
        return text

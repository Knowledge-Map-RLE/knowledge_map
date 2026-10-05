"""Проверки точного сохранённого источника и явных ошибок S3 без подмены редакции."""
from contextlib import asynccontextmanager

import pytest
from botocore.exceptions import ClientError

from domain.article_maps import ArticleMapError
from infrastructure.article_map_source import StoredArticleMapSource


class Repository:
    def authorize(self, *args):
        pass

    def session(self):
        return self

    @property
    def driver(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def run(self, *args, **kwargs):
        return self

    def single(self):
        return {'user_key': 'saved.md', 'formatted_key': 'other.md', 'raw_key': 'raw.md', 'bucket': 'source'}


class Storage:
    def __init__(self, code=None):
        self.code, self.keys, self.downloaded = code, [], []

    @asynccontextmanager
    async def client_context(self):
        yield self

    async def head_object(self, Bucket, Key):
        self.keys.append((Bucket, Key))
        if self.code:
            raise ClientError({'Error': {'Code': self.code, 'Message': 'private storage diagnostic'}}, 'HeadObject')

    async def download_text(self, bucket, key):
        self.downloaded.append((bucket, key))
        return 'Complete English article.\n\n## References\nBibliography retained.'


@pytest.mark.asyncio
async def test_reads_only_the_selected_complete_saved_revision():
    storage = Storage()
    source = StoredArticleMapSource(Repository(), storage, 'default')
    assert await source.available('article', 'owner') is True
    assert 'Bibliography retained.' in await source.read_text('article', 'owner')
    assert storage.downloaded == [('source', 'saved.md')]
    assert all(key == ('source', 'saved.md') for key in storage.keys)


@pytest.mark.asyncio
async def test_missing_selected_object_is_not_replaced_with_another_revision():
    storage = Storage('404')
    source = StoredArticleMapSource(Repository(), storage, 'default')
    assert await source.available('article', 'owner') is False
    with pytest.raises(ArticleMapError, match='missing'):
        await source.read_text('article', 'owner')
    assert storage.downloaded == []
    assert all(key == ('source', 'saved.md') for key in storage.keys)


@pytest.mark.parametrize('code', ['AccessDenied', 'ServiceUnavailable'])
@pytest.mark.asyncio
async def test_storage_failures_are_explicit_and_do_not_report_missing_text(code):
    source = StoredArticleMapSource(Repository(), Storage(code), 'default')
    with pytest.raises(ArticleMapError, match='storage request failed') as error:
        await source.available('article', 'owner')
    assert 'private' not in str(error.value)

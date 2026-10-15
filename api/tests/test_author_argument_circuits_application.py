"""Никаких неявных источников, AI-вызовов и публикации частичного результата."""
from copy import deepcopy
import socket
import pytest

from application.author_argument_circuits import SealAuthorArgumentCircuits
from domain.article_maps import ArticleMapError, ArticleMapAccessDenied
from infrastructure.development_prediction_store import FilePredictionStore
from tests.test_semantic_operator_graph import fixture
from tests.test_semantic_part_forecast import prepare
from tests.test_schema6_prediction import ref


class Maps:
    def __init__(self, maps): self.maps = {m['article_id']: m for m in maps}; self.reads = []
    def get(self, article, pipeline, owner, run):
        if owner != 'owner': raise ArticleMapAccessDenied('Owner mismatch')
        assert article in {'one', 'two'}
        self.reads.append(article); return deepcopy(self.maps[article])


def inputs():
    maps, origins = prepare([fixture(), fixture('two')])
    metadata = {'question': None, 'model_calls': 0, 'target_read': False, 'training_cutoff': '2022-12-31',
        'source_dates': {'one': '2010-01-01', 'two': '2011-01-01'}, 'excluded_source_sha256': ['0' * 64]}
    return maps, origins, metadata


def test_no_network_immutable_and_explicit_source_reads(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs): raise AssertionError('Network or AI forbidden')
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    import httpx
    monkeypatch.setattr(httpx.Client, 'send', forbidden)
    maps, origins, metadata = inputs(); port = Maps(maps); store = FilePredictionStore(tmp_path)
    use = SealAuthorArgumentCircuits(port, store)
    a = use.execute([ref('one'), ref('two')], 'owner', metadata, {}, None, origins)
    b = use.execute([ref('one'), ref('two')], 'owner', metadata, {}, None, origins)
    assert a == b and a['argument_circuits']['canonical_blocks'] == 6 and not a['target_read']
    assert port.reads == ['one', 'two', 'one', 'two'] and len(list(store.root.iterdir())) == 1


def test_future_source_rejected_before_any_map_access(tmp_path):
    maps, origins, metadata = inputs(); port = Maps(maps); metadata['source_dates']['two'] = '2023-01-01'
    with pytest.raises(ArticleMapError, match='Future'):
        SealAuthorArgumentCircuits(port, FilePredictionStore(tmp_path)).execute([ref('one'), ref('two')], 'owner', metadata, {}, None, origins)
    assert not port.reads and not list(tmp_path.iterdir())


def test_owner_and_excluded_target_do_not_publish(tmp_path):
    maps, origins, metadata = inputs(); port = Maps(maps); use = SealAuthorArgumentCircuits(port, FilePredictionStore(tmp_path))
    with pytest.raises(ArticleMapAccessDenied): use.execute([ref('one'), ref('two')], 'other', metadata, {}, None, origins)
    metadata['excluded_source_sha256'] = [maps[0]['source']['sha256']]
    with pytest.raises(ArticleMapError, match='Excluded target'): use.execute([ref('one'), ref('two')], 'owner', metadata, {}, None, origins)
    assert not list(tmp_path.iterdir())


def test_invalid_origin_preserves_existing_sealed_result(tmp_path):
    maps, origins, metadata = inputs(); store = FilePredictionStore(tmp_path)
    use = SealAuthorArgumentCircuits(Maps(maps), store)
    result = use.execute([ref('one'), ref('two')], 'owner', metadata, {}, None, origins)
    origins['sources'][0]['knowledge'][0]['knowledge_sha256'] = 'changed'
    with pytest.raises(ArticleMapError): use.execute([ref('one'), ref('two')], 'owner', metadata, {}, None, origins)
    assert store.read_seal(result['run_id']) == result and len(list(tmp_path.iterdir())) == 1

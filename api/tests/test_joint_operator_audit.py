"""Файловый сценарий проверяет входы и сохраняет неизменяемые артефакты без сети."""
from hashlib import sha256
import json
import socket

import pytest

from domain.article_maps import ArticleMapError
from tests.test_joint_operator_patterns import joint
from tools.audit_joint_operator_patterns import read_manifest, run


def manifest(tmp_path):
    snapshot = joint()
    path = tmp_path / 'map.json'
    raw = json.dumps(snapshot).encode()
    path.write_bytes(raw)
    config = {'version': 'joint-motif-explicit-inputs-1', 'sources': [{
        'article_id': snapshot['article_id'], 'run_id': snapshot['run_id'],
        'source_sha256': snapshot['source']['sha256'], 'path': str(path),
        'file_sha256': sha256(raw).hexdigest(), 'family': 'explicit-family'}]}
    config_path = tmp_path / 'manifest.json'
    config_path.write_text(json.dumps(config), encoding='utf-8')
    return config_path, config


def test_exact_manifest_and_target_exclusion(tmp_path):
    path, config = manifest(tmp_path)
    assert len(read_manifest(path, 'a' * 64)[1]) == 1
    with pytest.raises(ArticleMapError):
        read_manifest(path, config['sources'][0]['source_sha256'])
    config['sources'][0]['file_sha256'] = '0' * 64
    path.write_text(json.dumps(config), encoding='utf-8')
    with pytest.raises(ArticleMapError):
        read_manifest(path, 'a' * 64)


def test_repeat_and_corruption_with_network_forbidden(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Сетевой вызов в автономном сценарии')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    path, _ = manifest(tmp_path)
    output = tmp_path / 'results'
    first = run(path, output, 'a' * 64)
    hashes = {p.name: sha256(p.read_bytes()).hexdigest() for p in first.iterdir()}
    assert run(path, output, 'a' * 64) == first
    assert hashes == {p.name: sha256(p.read_bytes()).hexdigest() for p in first.iterdir()}
    (first / 'data.json').write_text('{}', encoding='utf-8')
    with pytest.raises(ArticleMapError):
        run(path, output, 'a' * 64)

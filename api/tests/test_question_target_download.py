"""Загрузка и чтение кэша цели запрещены до готовности запечатанного корпуса."""
from argparse import Namespace
from io import BytesIO
import json
from types import SimpleNamespace

import pytest

from domain.article_maps import ArticleMapError
from domain.article_maps import digest
from tools import download_question_evaluation_source as cli


@pytest.mark.parametrize("cached", [False, True])
@pytest.mark.parametrize("readiness", [None, {}, {"target_reading_allowed": False},
                                        {"target_reading_allowed": "true"}])
def test_unready_download_never_opens_target_network_or_cache(tmp_path, monkeypatch, cached, readiness):
    sealed = {"run_id": "0" * 64}
    if readiness is not None:
        sealed["readiness"] = readiness
    monkeypatch.setattr(cli, "FilePredictionStore", lambda root: SimpleNamespace(read_seal=lambda run: sealed))
    monkeypatch.setattr(cli.ctypes, "windll", SimpleNamespace(shell32=SimpleNamespace(IsUserAnAdmin=lambda: True)),
                        raising=False)
    monkeypatch.setattr(cli.urllib.request, "urlopen", lambda *a, **k: pytest.fail("Target network must stay closed"))
    monkeypatch.setattr(cli.Path, "read_text", lambda *a, **k: pytest.fail("Target cache must stay closed"))
    monkeypatch.setattr(cli.Path, "read_bytes", lambda *a, **k: pytest.fail("Target cache must stay closed"))
    args = Namespace(output=tmp_path, run_id="0" * 64, pmcid="PMC123", reuse_xml=tmp_path / "target.xml" if cached else None)
    with pytest.raises(ArticleMapError, match="readiness failed"):
        cli.run(args)
    assert list(tmp_path.iterdir()) == []


def test_download_requires_prediction_seal_first(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "FilePredictionStore", lambda root: SimpleNamespace(read_seal=lambda run: None))
    monkeypatch.setattr(cli.ctypes, "windll", SimpleNamespace(shell32=SimpleNamespace(IsUserAnAdmin=lambda: True)),
                        raising=False)
    monkeypatch.setattr(cli.urllib.request, "urlopen", lambda *a, **k: pytest.fail("No target request without seal"))
    args = Namespace(output=tmp_path, run_id="0" * 64, pmcid="PMC123", reuse_xml=None)
    with pytest.raises(ArticleMapError, match="Seal predictions"):
        cli.run(args)


@pytest.mark.parametrize("cached", [False, True])
def test_ready_download_keeps_exact_unicode_and_accepts_verified_cache(tmp_path, monkeypatch, cached):
    monkeypatch.setattr(cli, "FilePredictionStore", lambda root: SimpleNamespace(
        read_seal=lambda run: {"readiness": {"target_reading_allowed": True}}))
    monkeypatch.setattr(cli.ctypes, "windll", SimpleNamespace(shell32=SimpleNamespace(IsUserAnAdmin=lambda: True)),
                        raising=False)
    xml = '<article><front><article-meta><title-group><article-title>Fixture</article-title></title-group></article-meta></front><body><sec><title>Methods</title><p>Plasma 😀.</p></sec><sec><title>Results</title><p>Observed fixture.</p></sec></body></article>'
    requests = []
    def response(url, **kwargs):
        requests.append(url)
        if url.endswith('/fullTextXML'):
            return BytesIO(xml.encode('utf-8'))
        return BytesIO(json.dumps({'resultList': {'result': [{'pmcid': 'PMC123', 'title': 'Fixture',
            'doi': 'fixture-doi', 'firstPublicationDate': '2024-01-01'}]}}).encode('utf-8'))
    monkeypatch.setattr(cli.urllib.request, 'urlopen', response)
    cached_xml = tmp_path / 'cache' / 'article.xml' if cached else None
    if cached:
        cached_xml.parent.mkdir()
        cached_xml.write_text(xml, encoding='utf-8')
        cached_xml.with_name('metadata.json').write_text(json.dumps({'pmcid': 'PMC123', 'xml_sha256': digest(xml),
            'title': 'Fixture', 'doi': 'fixture-doi', 'available_on': '2024-01-01'}), encoding='utf-8')
    args = Namespace(output=tmp_path / 'output', run_id='0' * 64, pmcid='PMC123', reuse_xml=cached_xml)
    result = cli.run(args)
    folder = cli.Path(result['folder'])
    assert (folder / 'article.xml').read_text(encoding='utf-8') == xml
    markdown = (folder / 'article.md').read_text(encoding='utf-8')
    assert 'Plasma 😀.' in markdown and result['source_sha256'] == digest(markdown)
    assert result['model_calls'] == 0 and len(requests) == (0 if cached else 2)

"""Библиография в body и back не теряется и не становится знанием графа."""
from hashlib import sha256
import pytest

from domain.article_maps import ArticleMapError, prepare_source
from infrastructure.primary_article_xml import materialize_primary_article


def xml(in_body=True):
    refs = '<ref-list><ref id="r1"><mixed-citation>Reference one.</mixed-citation></ref><ref id="r2">Reference two.</ref></ref-list>'
    return ('<article><front><article-meta><article-id pub-id-type="pmcid">PMC123</article-id>'
            '<article-id pub-id-type="doi">10.1/example</article-id><title-group><article-title>Study 🐁</article-title></title-group>'
            '<permissions><license>CC BY</license></permissions><abstract>Study abstract.</abstract></article-meta></front>'
            '<body><sec><title>Results</title><p>Before<fig id="F1"><label>Figure 1</label><caption><p>Result caption.</p></caption></fig> after.</p>'
            '<table-wrap><caption><p>Table caption.</p></caption><table><tr><th>Group</th><th>Value</th></tr><tr><td>A</td><td>0.1</td></tr></table>'
            '<table-wrap-foot><p>Explicit units.</p></table-wrap-foot></table-wrap></sec>'
            + ('<sec><title>References</title>' + refs + '</sec>' if in_body else '') +
            '<sec><title>Data Availability</title><p>Data may be requested.</p></sec></body>'
            + ('' if in_body else '<back>' + refs + '</back>') + '</article>').encode()


@pytest.mark.parametrize('in_body', [True, False])
def test_every_reference_preserved_after_graph_boundary_with_coordinates(in_body):
    packet = materialize_primary_article(xml(in_body), 'PMC123', '10.1/example'); source = packet['source']
    assert packet['reference_count'] == 2
    assert 'Reference one.' in source['text'][source['content_end']:]
    assert all('Reference one.' not in u['text'] for u in source['units'])
    assert any(u['text'] == 'Data may be requested.' for u in source['units'])
    assert all(source['text'][u['start']:u['end']] == u['text'] and sha256(u['text'].encode()).hexdigest() == u['sha256'] for u in source['units'])
    prepared = prepare_source('study', source['text'])
    assert prepared['references_excluded'] and len(prepared['units']) == len(source['units'])


def test_embedded_caption_is_not_duplicated_and_table_rows_are_preserved():
    packet = materialize_primary_article(xml(), 'PMC123', '10.1/example'); units = packet['source']['units']
    assert sum('Result caption.' in u['text'] for u in units) == 1
    assert any(u['text'] == 'Before after.' for u in units)
    assert [u['text'] for u in units if u['kind'] == 'table_row'] == ['Group | Value', 'A | 0.1']
    assert any(u['text'] == 'Explicit units.' for u in units)


@pytest.mark.parametrize('pmcid,doi', [('PMC999', '10.1/example'), ('PMC123', '10.2/other')])
def test_wrong_primary_identity_prevents_source_publication(pmcid, doi):
    with pytest.raises(ArticleMapError): materialize_primary_article(xml(), pmcid, doi)

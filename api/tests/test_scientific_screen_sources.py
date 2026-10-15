"""Полный источник и точные координаты не заменяются аннотацией."""
from hashlib import sha256
import pytest
from infrastructure.scientific_screen_sources import parse_scientific_xml

XML = '<article xmlns="urn:test"><front><article-meta><article-id pub-id-type="pmc">123</article-id><article-id pub-id-type="doi">10.test/a</article-id><title-group><article-title>Study</article-title></title-group><abstract><p>Abstract α.</p></abstract></article-meta></front><body><sec><title>Methods</title><p>Mouse 🐁 model.</p><fig><caption><p>Figure α.</p></caption></fig><table-wrap><caption><p>Groups.</p></caption><table><tr><th>Group</th><th>N</th></tr><tr><td>A</td><td>4</td></tr></table></table-wrap><ref-list><ref>One reference.</ref></ref-list></sec></body></article>'


def test_full_bibliography_captions_table_and_unicode():
    s, c = parse_scientific_xml(XML.encode(), 'PMC123', '10.test/a')
    assert c['references_preserved'] == c['references'] == 1
    assert c['captions_preserved'] == c['captions'] == 2
    assert c['tables'] == c['text_tables'] == 1 and 'A | 4' in s['text']
    assert sha256(s['text'].encode()).hexdigest() == s['sha256']
    for u in s['units']: assert s['text'][u['start']:u['end']] == u['text']
    assert 'One reference.' not in s['text'][:s['content_end']]


@pytest.mark.parametrize('pmcid,doi', [('PMC124', '10.test/a'), ('PMC123', '10.test/b')])
def test_wrong_identity_rejected(pmcid, doi):
    with pytest.raises(ValueError): parse_scientific_xml(XML.encode(), pmcid, doi)


def test_abstract_only_rejected():
    with pytest.raises(ValueError): parse_scientific_xml(XML.split('<body>')[0].encode() + b'</article>', 'PMC123', '10.test/a')

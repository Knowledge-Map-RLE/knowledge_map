"""Разделение контрольных источников не открывает результаты генератору."""
from hashlib import sha256
import xml.etree.ElementTree as ET

import pytest

from domain.article_maps import ArticleMapError
from infrastructure.control_method_packets import method_packet


def xml(method_title='Materials and methods', body_type='research-article'):
    return f'''<article article-type="{body_type}"><front><article-meta>
      <article-id pub-id-type="pmc">123</article-id><article-id pub-id-type="doi">10.1/example</article-id>
      <abstract><p>Скрытый исход аннотации</p></abstract></article-meta></front><body>
      <sec><title>Introduction</title><p>Предшествующая гипотеза</p></sec>
      <sec><title>{method_title}</title><p>Мыши 🐁 получили 5 μl.</p>
        <sec><title>Results</title><p>Не открывать результат</p></sec>
        <sec><title>Animals</title><p>Human TNFR1 transgenic mice.</p></sec></sec>
      <sec><title>Results</title><p>Не открывать результат</p></sec>
      <sec><title>Discussion</title><p>Скрытый исход обсуждения</p></sec>
      </body></article>'''.encode()


def test_only_explicit_methods_with_unicode_and_xpath():
    raw = xml(); p = method_packet(raw, 'PMC123', '10.1/example'); source = p['method_source']
    assert p['raw_xml_sha256'] == sha256(raw).hexdigest() and p['has_explicit_methods']
    assert '🐁' in source['text'] and 'Human TNFR1' in source['text']
    assert 'Не открывать' not in source['text'] and 'Скрытый исход' not in source['text']
    assert 'Предшествующая гипотеза' not in source['text']
    for u in source['units']:
        assert source['text'][u['start']:u['end']] == u['text']
        assert sha256(u['text'].encode()).hexdigest() == u['sha256']
        assert u['xpath'].startswith('/article[1]/body[1]/sec[2]/')
    assert source['coordinate_space'] == 'selected_method_text'
    assert not p['generator_access'] and not p['training_source'] and not p['results_section_included']


@pytest.mark.parametrize('title', ['Methods', '2. Materials and methods', 'Experimental procedures'])
def test_explicit_registered_method_headings(title):
    assert method_packet(xml(title), 'PMC123', '10.1/example')['has_explicit_methods']


@pytest.mark.parametrize('title', ['Results and methods', 'Main text', 'Discussion'])
def test_unknown_or_combined_sections_do_not_disguise_results_as_methods(title):
    p = method_packet(xml(title), 'PMC123', '10.1/example')
    assert not p['has_explicit_methods'] and p['method_source']['text'] == ''


@pytest.mark.parametrize('pmcid,doi', [('PMC999', '10.1/example'), ('PMC123', '10.1/other')])
def test_identity_must_match_registered_control(pmcid, doi):
    with pytest.raises(ArticleMapError): method_packet(xml(), pmcid, doi)


def test_namespace_and_no_implicit_method_fallback():
    raw = xml().replace(b'<article ', b'<article xmlns="urn:test" ')
    p = method_packet(raw, 'PMC123', '10.1/example')
    assert p['has_explicit_methods'] and p['article_type'] == 'research-article'


def test_truncated_control_xml_is_not_repaired():
    with pytest.raises(ET.ParseError): method_packet(xml()[:-10], 'PMC123', '10.1/example')


def test_result_figures_in_methods_and_inside_paragraphs_are_removed_with_tail_preserved():
    raw = xml().replace(b'<p>Human TNFR1 transgenic mice.</p>',
        b'<fig><caption><p>SECRET result caption</p></caption></fig>'
        b'<p>Before <fig><caption><p>SECRET embedded result</p></caption></fig>after.</p>'
        b'<table-wrap><table><tr><td>SECRET result table</td></tr></table></table-wrap>')
    p = method_packet(raw, 'PMC123', '10.1/example'); s = p['method_source']['text']
    assert 'SECRET' not in s and 'Before after.' in s
    assert all(u['kind'] not in {'fig', 'table-wrap'} for u in p['method_source']['units'])


def test_result_section_nested_in_paragraph_is_not_flattened_into_methods():
    raw = xml().replace(b'<p>Human TNFR1 transgenic mice.</p>',
        b'<p>Before <sec><title>Results</title><p>SECRET</p></sec>after.</p>')
    s = method_packet(raw, 'PMC123', '10.1/example')['method_source']['text']
    assert 'SECRET' not in s and 'Before after.' in s

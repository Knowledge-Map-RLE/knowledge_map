"""Регрессия полной библиографии внутри body и сохранения подписей и таблиц."""
import importlib.util
from pathlib import Path


def converter():
    path = Path(__file__).resolve().parents[2] / 'eval/whole_map_forecast/mechanistic-opportunities-v1/prepare_control.py'
    spec = importlib.util.spec_from_file_location('mechanistic_control_source', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def test_references_inside_body_are_preserved_outside_scientific_boundary():
    xml = b'''<article><front><article-meta><title-group><article-title>Test</article-title></title-group>
      <abstract><p>Abstract</p></abstract></article-meta></front><body><sec><title>Results</title><p>Own result</p></sec>
      <sec><title>References</title><ref-list><ref id="R1"><label>1.</label><mixed-citation>Reference-only marker</mixed-citation></ref></ref-list></sec></body></article>'''
    source, coverage = converter().extract(xml)
    assert 'Reference-only marker' not in source['text'][:source['content_end']]
    assert 'Reference-only marker' in source['text'][source['content_end']:]
    assert coverage['references'] == coverage['references_preserved'] == 1


def test_namespaced_table_and_figure_caption_keep_unicode_coordinates():
    xml = '''<article><front><article-meta><title-group><article-title>Test</article-title></title-group></article-meta></front>
      <body><sec><title>Results</title><p>Own result 🙂</p><fig><caption><p>Unique figure caption</p></caption></fig>
      <table-wrap xmlns:h="http://www.w3.org/1999/xhtml"><h:table><h:tr><h:td>Unique cell β</h:td></h:tr></h:table></table-wrap></sec></body></article>'''.encode()
    source, coverage = converter().extract(xml)
    assert coverage['xml_tables'] == coverage['text_tables'] == 1
    assert coverage['captions'] == coverage['captions_preserved'] == 1
    assert 'Unique cell β' in source['text'][:source['content_end']]
    assert all(source['text'][u['start']:u['end']] == u['text'] for u in source['units'])

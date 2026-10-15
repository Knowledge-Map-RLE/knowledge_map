"""Дословная ревизия сохраняет слова, координаты и отдельную библиографию."""
from hashlib import sha256
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

from domain.article_maps import ArticleMapError
from tools.prepare_manly_complete_source import NS, build, regions


def fixture(tmp_path):
    pdf = tmp_path / 'synthetic.pdf'
    pdf.write_bytes(b'synthetic fixture, not a scientific article')
    intake = tmp_path / 'intake.json'
    intake.write_text(json.dumps({'id': 'manly2008', 'pdf_sha256': sha256(pdf.read_bytes()).hexdigest()}))
    tree = ET.Element(NS + 'html')
    for page in range(1, 14):
        item = ET.SubElement(tree, NS + 'page', width='594', height='783')
        for text, y in ((f'synthetic-{page}', 60), ('synthetic-footer', 750)):
            ET.SubElement(item, NS + 'word', xMin='60', xMax='90', yMin=str(y), yMax=str(y + 8)).text = text
    bbox = tmp_path / 'bbox.xml'
    ET.ElementTree(tree).write(bbox, encoding='utf-8')
    (tmp_path / 'pdf-page-02.png').write_bytes(b'synthetic rendered-fixture identity')
    return pdf, bbox, intake


def test_word_conservation_and_unicode_bindings(tmp_path):
    text, source, proof = build(*fixture(tmp_path), tmp_path)
    assert proof['pdf_word_count'] == 26
    assert proof['retained_word_count'] == proof['excluded_footer_word_count'] == 13
    assert all(text[w['start']:w['end']] == w['text'] for w in proof['words'])
    assert all(w['end'] <= source['content_end'] for w in proof['words'] if w['category'] == 'body')
    assert all(w['start'] >= source['content_end'] for w in proof['words'] if w['category'] == 'references')
    assert proof['summarized_source_paragraphs'] == 0


def test_regions_cover_body_once_and_preserve_reference_column():
    assert regions(12)[-1][-1] == 'references'
    for page in range(1, 14):
        for x in (60, 295, 310, 535):
            for y in (60, 150, 205, 300, 410, 600, 730):
                assigned = [r for r in regions(page) if r[1] <= x < r[3] and r[2] <= y < r[4]]
                assert len(assigned) == 1


def test_changed_pdf_rejected_before_source_creation(tmp_path):
    paths = fixture(tmp_path)
    paths[0].write_bytes(b'a different PDF')
    with pytest.raises(ArticleMapError):
        build(*paths, tmp_path)

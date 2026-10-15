"""Полный XML-источник для адресного скрининга, без извлечения знаний и AI."""
from hashlib import sha256
import xml.etree.ElementTree as ET
from domain.article_maps import require


def local(node):
    return node.tag.rsplit('}', 1)[-1]


def flat(node):
    return ' '.join(''.join(node.itertext()).split())


def parse_scientific_xml(raw, pmcid, doi):
    root = ET.fromstring(raw)
    meta = next((n for n in root.iter() if local(n) == 'article-meta'), None)
    body = next((n for n in root if local(n) == 'body'), None)
    require(meta is not None and body is not None, 'Full primary article front and body required')
    ids = {n.get('pub-id-type'): flat(n) for n in meta if local(n) == 'article-id'}
    require(ids.get('doi', '').lower() == doi.lower(), 'Primary source DOI differs')
    pmc_ids = [v for k, v in ids.items() if k in {'pmc', 'pmcid'}]
    require(any(v.removeprefix('PMC') == pmcid.removeprefix('PMC') for v in pmc_ids), 'Primary source PMCID differs')
    units = []; text = ''
    def append(value, tag, section):
        nonlocal text
        if not value: return
        start = len(text); text += value
        units.append({'id': 'U' + str(len(units) + 1), 'start': start, 'end': len(text), 'tag': tag, 'section': section, 'text': value})
        text += '\n\n'
    def table_text(table):
        return '\n'.join(' | '.join(flat(c) for c in row if local(c) in {'td', 'th'})
                         for row in table.iter() if local(row) == 'tr')
    def visit(node, section):
        tag = local(node)
        if tag == 'ref-list': return
        if tag == 'sec': section = next((flat(n) for n in node if local(n) == 'title'), section)
        if tag in {'article-title', 'title', 'p', 'table', 'caption'}:
            append(table_text(node) if tag == 'table' else flat(node), tag, section); return
        for child in node: visit(child, section)
    title = next((flat(n) for n in meta.iter() if local(n) == 'article-title'), '')
    require(title, 'Scientific source title required')
    append(title, 'article-title', 'Title')
    for child in meta:
        if local(child) == 'abstract': visit(child, 'Abstract')
    visit(body, 'Body'); content_end = len(text)
    refs = [n for n in root.iter() if local(n) == 'ref']; append('References', 'title', 'References')
    for n in refs: append(flat(n), 'ref', 'References')
    source = {'version': 'explicit-primary-screen-xml-1', 'pmcid': pmcid, 'doi': doi, 'title': title,
              'text': text, 'sha256': sha256(text.encode()).hexdigest(), 'xml_sha256': sha256(raw).hexdigest(),
              'units': units, 'content_end': content_end, 'offset_encoding': 'unicode_codepoints',
              'references_excluded_from_analysis': True, 'model_calls': 0}
    captions = [flat(n) for n in root.iter() if local(n) == 'caption']
    coverage = {'references': len(refs), 'references_preserved': sum(flat(n) in text[content_end:] for n in refs),
                'tables': sum(local(n) == 'table' for n in root.iter()), 'text_tables': sum(u['tag'] == 'table' for u in units),
                'captions': len(captions), 'captions_preserved': sum(c in text[:content_end] for c in captions),
                'coordinate_unit': 'unicode_codepoints', 'source_sha256': source['sha256']}
    require(coverage['references'] == coverage['references_preserved'] and coverage['tables'] == coverage['text_tables']
            and coverage['captions'] == coverage['captions_preserved'], 'Incomplete primary source conversion')
    return source, coverage

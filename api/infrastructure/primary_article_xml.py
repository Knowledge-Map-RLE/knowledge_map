"""Полный XML первичной статьи: библиография отделяется независимо от её размещения."""
from copy import deepcopy
from hashlib import sha256
import xml.etree.ElementTree as ET

from domain.article_maps import require

VERSION = 'primary-article-xml-source-1'


def tag(n):
    return n.tag.rsplit('}', 1)[-1]


def child(n, name):
    return next((c for c in n if tag(c) == name), None)


def text(n):
    return ' '.join(''.join(n.itertext()).split()) if n is not None else ''


def materialize_primary_article(raw, pmcid, doi):
    root = ET.fromstring(raw)
    require(tag(root) == 'article', 'Exactly one primary XML article root required')
    front = child(root, 'front'); require(front is not None, 'Primary XML front required')
    meta = child(front, 'article-meta'); require(meta is not None, 'Primary article metadata required')
    identifiers = {n.get('pub-id-type'): text(n) for n in meta if tag(n) == 'article-id'}
    reported = [v for k, v in identifiers.items() if k in {'pmc', 'pmcid'}]
    require(reported and all(v.removeprefix('PMC') == pmcid.removeprefix('PMC') for v in reported), 'Primary PMCID differs')
    require(identifiers.get('doi', '').casefold() == doi.casefold(), 'Primary DOI differs')
    body = child(root, 'body'); require(body is not None and bool(text(body)), 'Primary full body required')
    paths = {}
    def locate(n, path):
        paths[id(n)] = path; counts = {}
        for c in n:
            name = tag(c); counts[name] = counts.get(name, 0) + 1
            locate(c, path + '/' + name + '[' + str(counts[name]) + ']')
    locate(root, '/article[1]')
    ref_lists = [n for n in root.iter() if tag(n) == 'ref-list']
    references = [r for rl in ref_lists for r in rl if tag(r) == 'ref']
    require(references and len({paths[id(r)] for r in references}) == len(references), 'Explicit complete reference list required')
    title_group = child(meta, 'title-group'); title = text(child(title_group, 'article-title')) if title_group is not None else ''
    require(title, 'Primary article title required')
    chunks = [('title', title, 'Title', paths[id(title_group)])]
    for n in meta:
        if tag(n) == 'abstract': chunks.append(('abstract', text(n), 'Abstract', paths[id(n)]))
    def without_displays(n):
        copy = deepcopy(n)
        def remove(parent):
            previous = None
            for c in list(parent):
                if tag(c) in {'fig', 'table-wrap', 'ref-list'}:
                    if c.tail:
                        if previous is None: parent.text = (parent.text or '') + c.tail
                        else: previous.tail = (previous.tail or '') + c.tail
                    parent.remove(c)
                else:
                    remove(c); previous = c
        remove(copy)
        return text(copy)
    def visit(n, section):
        name = tag(n)
        if name == 'ref-list': return
        if name == 'sec':
            heading = text(child(n, 'title')) or section
            if heading.casefold() in {'references', 'bibliography'}:
                # Список сохраняется ниже, не попадает в содержательные единицы.
                return
            if heading != section: chunks.append(('heading', '## ' + heading, heading, paths[id(n)]))
            for c in n:
                if tag(c) != 'title': visit(c, heading)
        elif name == 'fig':
            value = '\n'.join(v for v in (text(child(n, 'label')), text(child(n, 'caption'))) if v)
            chunks.append(('figure_caption', value, section, paths[id(n)]))
        elif name == 'table-wrap':
            value = '\n'.join(v for v in (text(child(n, 'label')), text(child(n, 'caption'))) if v)
            chunks.append(('table_caption', value, section, paths[id(n)]))
            for row in n.iter():
                if tag(row) == 'tr':
                    values = [text(c) for c in row if tag(c) in {'th', 'td'}]
                    if values: chunks.append(('table_row', ' | '.join(values), section, paths[id(row)]))
            for foot in n:
                if tag(foot) == 'table-wrap-foot': chunks.append(('table_note', text(foot), section, paths[id(foot)]))
        elif name in {'p', 'list', 'boxed-text', 'disp-quote', 'disp-formula'}:
            chunks.append((name, without_displays(n), section, paths[id(n)]))
            def displays(container):
                for c in container:
                    if tag(c) in {'fig', 'table-wrap'}: visit(c, section)
                    else: displays(c)
            displays(n)
        else:
            for c in n: visit(c, section)
    visit(body, 'Main text')
    pieces, units = [], []; cursor = 0
    for kind, value, section, xpath in chunks:
        if not value: continue
        if pieces: pieces.append('\n\n'); cursor += 2
        start = cursor; pieces.append(value); cursor += len(value)
        units.append({'id': 'U' + str(len(units) + 1), 'start': start, 'end': cursor, 'kind': kind,
                      'section': section, 'text': value, 'xpath': xpath, 'sha256': sha256(value.encode()).hexdigest()})
    content_end = cursor
    pieces.append('\n\n## References\n\n')
    reference_units = []
    for i, r in enumerate(references):
        if i: pieces.append('\n\n')
        pieces.append(text(r)); reference_units.append({'id': r.get('id'), 'xpath': paths[id(r)], 'text': text(r)})
    document = ''.join(pieces)
    require(all(document[u['start']:u['end']] == u['text'] for u in units), 'Primary Unicode coordinates differ')
    dates = []
    for n in meta:
        if tag(n) == 'pub-date':
            dates.append({'attributes': dict(n.attrib), **{f: text(child(n, f)) for f in ('year', 'month', 'day')}})
    return {'version': VERSION, 'pmcid': pmcid, 'doi': doi.casefold(), 'title': title, 'identifiers': identifiers,
            'publication_dates': dates, 'license': text(child(meta, 'permissions')), 'raw_xml_sha256': sha256(raw).hexdigest(),
            'reference_count': len(references), 'references': reference_units,
            'reference_list_paths': [paths[id(r)] for r in ref_lists],
            'source': {'text': document, 'sha256': sha256(document.encode()).hexdigest(), 'content_end': content_end,
                       'offset_encoding': 'unicode_codepoints', 'units': units},
            'model_calls': 0, 'expert_validated': False, 'figure_images_interpreted': False,
            'supplements_downloaded': False,
            'limitations_ru': 'Сохранены текст, строки таблиц, примечания и подписи. Значения из изображений '
                              'и непрочитанных дополнительных файлов не восстанавливаются. Библиография '
                              'перенесена в отдельный заключительный раздел; координаты относятся к этому Markdown.'}

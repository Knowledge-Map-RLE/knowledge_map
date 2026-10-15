"""Контрольные XML раскрывают только явно выделенные методы, сохраняя сырой источник отдельно."""
from hashlib import sha256
from copy import deepcopy
import re
import xml.etree.ElementTree as ET

from domain.article_maps import require

VERSION = 'controlled-article-method-packet-2'
METHOD_TITLES = {'methods', 'materials and methods', 'methods and materials', 'experimental procedures', 'material and methods'}
METHOD_TYPES = {'methods', 'materials-methods', 'materials_and_methods'}
OUTCOME_TITLES = {'results', 'discussion', 'results and discussion', 'conclusions', 'conclusion'}
EXCLUDED_DISPLAYS = {'fig', 'table-wrap', 'supplementary-material', 'ref-list', 'abstract'}


def tag(node): return node.tag.rsplit('}', 1)[-1]
def text(node): return ' '.join(''.join(node.itertext()).split()) if node is not None else ''
def child(node, name): return next((c for c in node if tag(c) == name), None)
def heading(node): return re.sub(r'^\d+(?:\.\d+)*\.?\s+', '', text(child(node, 'title'))).casefold()


def filtered_text(node):
    node = deepcopy(node)
    def remove(parent):
        previous = None
        for n in list(parent):
            excluded = tag(n) in EXCLUDED_DISPLAYS or tag(n) == 'sec' and (heading(n) in OUTCOME_TITLES
                or n.get('sec-type') in {'results', 'discussion'} or 'results' in heading(n))
            if excluded:
                # Текст после удалённой подписи относится к абзацу и сохраняется.
                if n.tail:
                    if previous is None: parent.text = (parent.text or '') + n.tail
                    else: previous.tail = (previous.tail or '') + n.tail
                parent.remove(n)
            else: remove(n); previous = n
    remove(node)
    return text(node)


def method_packet(raw, pmcid, doi):
    root = ET.fromstring(raw)
    articles = [n for n in root.iter() if tag(n) == 'article']
    require(len(articles) == 1, 'Exactly one control article required')
    article = articles[0]; front = child(article, 'front'); require(front is not None, 'Article metadata required')
    meta = child(front, 'article-meta'); require(meta is not None, 'Article metadata required')
    ids = {n.get('pub-id-type'): text(n) for n in meta if tag(n) == 'article-id'}
    pmcids = [v for k, v in ids.items() if k in {'pmc', 'pmcid'}]
    require(pmcids and all(v.removeprefix('PMC') == pmcid.removeprefix('PMC') for v in pmcids), 'Control PMCID differs')
    require(ids.get('doi', '').casefold() == doi.casefold(), 'Control DOI differs')
    body = child(article, 'body'); require(body is not None, 'Full control article body required')
    paths = {}
    def locate(node, path):
        paths[id(node)] = path; counts = {}
        for n in node:
            name = tag(n); counts[name] = counts.get(name, 0) + 1
            locate(n, path + '/' + name + '[' + str(counts[name]) + ']')
    locate(root, '/' + tag(root) + '[1]')
    sections = []
    def find(node):
        if tag(node) == 'sec' and (node.get('sec-type') in METHOD_TYPES or heading(node) in METHOD_TITLES):
            # Объединённый заголовок не лицензирует результат даже при ошибочном sec-type.
            if heading(node) in OUTCOME_TITLES or 'results' in heading(node): return
            sections.append(node); return
        for n in node: find(n)
    find(body)
    chunks = []
    def collect(node):
        if tag(node) in EXCLUDED_DISPLAYS: return
        if tag(node) == 'sec' and (heading(node) in OUTCOME_TITLES or node.get('sec-type') in {'results', 'discussion'}
                                 or 'results' in heading(node)): return
        if tag(node) in {'title', 'p', 'list', 'disp-formula'}:
            value = filtered_text(node)
            if value: chunks.append((paths[id(node)], tag(node), value))
            return
        for n in node: collect(n)
    for section in sections: collect(section)
    pieces = []; units = []; cursor = 0
    for xpath, kind, value in chunks:
        if pieces: pieces.append('\n\n'); cursor += 2
        start = cursor; pieces.append(value); cursor += len(value)
        units.append({'id': 'M' + str(len(units) + 1), 'xpath': xpath, 'kind': kind, 'text': value,
            'start': start, 'end': cursor, 'sha256': sha256(value.encode()).hexdigest()})
    source = ''.join(pieces)
    dates = [{'attributes': dict(n.attrib), 'text': text(n)} for n in meta if tag(n) == 'pub-date']
    return {'version': VERSION, 'pmcid': pmcid, 'doi': doi.casefold(), 'raw_xml_sha256': sha256(raw).hexdigest(),
        'article_type': article.get('article-type'), 'publication_dates': dates,
        'declared_method_sections': [{'xpath': paths[id(n)], 'heading': text(child(n, 'title')), 'sec_type': n.get('sec-type')} for n in sections],
        'method_source': {'text': source, 'sha256': sha256(source.encode()).hexdigest(), 'units': units,
            'offset_encoding': 'unicode_codepoints', 'coordinate_space': 'selected_method_text',
            'xpath_dialect': 'namespace_agnostic_indexed_elements', 'omitted_descendant_tags': sorted(EXCLUDED_DISPLAYS)},
        'has_explicit_methods': bool(sections and units), 'abstract_included': False, 'results_section_included': False,
        'training_source': False, 'generator_access': False, 'model_calls': 0, 'expert_validated': False,
        'figure_images_interpreted': False, 'supplements_downloaded': False,
        'limitations_ru': 'Отобраны только явно названные разделы методов; текст методов может содержать '
            'авторские замечания об исходах, поэтому извлечение раздела не удостоверяет слепоту человека. '
            'Рисунки, таблицы и дополнительные материалы исключены, даже если вложены в методический абзац; '
            'их методические сведения здесь тоже недоступны и не восстанавливаются по догадке. '
            'Координаты относятся к отобранному тексту, а XPath и хеш — к отдельному полному XML. '
            'Отсутствие такого раздела не доказывает, что в статье нет описания метода.'}

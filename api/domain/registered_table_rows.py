"""Строгое чтение зарегистрированных табличных ячеек с исходными координатами."""
from hashlib import sha256
import re

from domain.article_maps import require

VERSION = 'registered-source-table-cells-1'
NUMBER = r'(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?'


def parse_row(source, uid, pattern, fields):
    unit = next((u for u in source['units'] if u['id'] == uid), None)
    require(unit is not None and 0 <= unit['start'] < unit['end'] <= source['content_end']
            and source['text'][unit['start']:unit['end']] == unit['text'], 'Table source coordinates differ')
    match = re.fullmatch(pattern, unit['text'])
    require(match is not None and set(match.groupdict()) == set(fields), 'Registered table row differs from source')
    cells = []
    for name, spec in fields.items():
        require(isinstance(spec, dict) and set(spec) == {'kind', 'unit'}
                and spec['kind'] in {'count', 'estimate', 'confidence_bound', 'exposure_time', 'mean', 'sample_proportion'}
                and isinstance(spec['unit'], str) and bool(spec['unit']), 'Explicit cell type and unit required')
        raw = match.group(name)
        value = raw.replace(',', '')
        require(re.fullmatch(NUMBER, raw) is not None, 'Unsupported table number')
        if spec['kind'] == 'count':
            require('.' not in value, 'A count cannot silently become a decimal')
        start, end = match.span(name)
        cells.append({'column': name, 'value': value, 'printed_value': raw, **spec,
                      'source_span': {'start': unit['start'] + start, 'end': unit['start'] + end},
                      'source_unit_id': uid})
    return {'cells': cells, 'source_unit_id': uid,
            'source_evidence': {'start': unit['start'], 'end': unit['end'], 'text': unit['text'],
                                'sha256': sha256(unit['text'].encode()).hexdigest()}}


def numeric_group(name):
    return '(?P<' + name + '>' + NUMBER + ')'


def rate_columns(prefix):
    return {prefix + 'cases': {'kind': 'count', 'unit': 'cases'},
            prefix + 'rate': {'kind': 'estimate', 'unit': 'per 100 person-years'},
            prefix + 'low': {'kind': 'confidence_bound', 'unit': 'per 100 person-years'},
            prefix + 'high': {'kind': 'confidence_bound', 'unit': 'per 100 person-years'}}


def rate_pattern(prefix, *, separate_bounds=False):
    cells = numeric_group(prefix + 'cases') + r'\s+' + numeric_group(prefix + 'rate') + r'%\s+'
    if separate_bounds:
        return cells + numeric_group(prefix + 'low') + r'%\s+' + numeric_group(prefix + 'high') + '%'
    return cells + r'\(' + numeric_group(prefix + 'low') + '[–-]' + numeric_group(prefix + 'high') + r'\)'

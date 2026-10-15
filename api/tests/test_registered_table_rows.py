"""Числовые ячейки сохраняют единицы и исходные позиции, не выводя эффект."""
import re

import pytest

from domain.article_maps import ArticleMapError, prepare_source
from domain.registered_table_rows import parse_row, numeric_group, rate_columns, rate_pattern


def test_rate_is_not_silently_converted_to_risk_percent():
    text = 'Group 1,800 12.5% (10.0–15.0)\n\n# References\nNone'
    source = prepare_source('synthetic', text)
    fields = {'n': {'kind': 'count', 'unit': 'participants'},
              **{k: v for k, v in rate_columns('').items() if k != 'cases'}}
    pattern = 'Group ' + numeric_group('n') + r'\s+' + numeric_group('rate') + r'% \(' + numeric_group('low') + '[–-]' + numeric_group('high') + r'\)'
    result = parse_row(source, 'U1', pattern, fields)
    assert result['cells'][0]['value'] == '1800'
    assert result['cells'][1]['unit'] == 'per 100 person-years'
    assert all(text[c['source_span']['start']:c['source_span']['end']] == c['printed_value'] for c in result['cells'])


@pytest.mark.parametrize('raw', ['1,,800', '18,00', '1.5'])
def test_malformed_thousands_or_noninteger_count_rejected(raw):
    source = prepare_source('synthetic', 'Group ' + raw + '\n\n# References\nNone')
    with pytest.raises(ArticleMapError):
        parse_row(source, 'U1', 'Group ' + numeric_group('n'), {'n': {'kind': 'count', 'unit': 'participants'}})


def test_truncated_or_changed_source_is_rejected():
    source = prepare_source('synthetic', 'Group 5\n\n# References\nNone')
    source['units'][0]['text'] = 'Group 6'
    with pytest.raises(ArticleMapError):
        parse_row(source, 'U1', 'Group ' + numeric_group('n'), {'n': {'kind': 'count', 'unit': 'participants'}})

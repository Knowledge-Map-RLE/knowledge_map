"""Табличная семантика не смешивает исходные группы и уровни неопределённости."""
from tools.author_manly_table_records import authored_items


def row(table, context):
    columns = [('subjects', '20', 'participants'), ('person_years', '50', 'person-years'),
               ('cases', '2', 'cases'), ('rate', '4', 'per 100 person-years'),
               ('low', '1', 'per 100 person-years'), ('high', '7', 'per 100 person-years')]
    return {'table': table, 'row_index': 2, 'id': 'synthetic-row', 'label_en': 'Age 65-69 yr',
            'label_ru': 'Синтетическая возрастная группа', 'source_unit_id': 'synthetic-unit',
            'context': {'header_units': ['synthetic-header'], **context},
            'cells': [{'column': n, 'value': value, 'printed_value': value, 'unit': unit} for n, value, unit in columns]}


def test_baseline_memory_group_and_95_percent_interval_are_preserved():
    item = authored_items([row(3, {'baseline_group': 'memory-heading',
                                  'population_attribution_status': 'age-subtotal and parent n disagree'})])[0]
    assert item['roles']['baseline_group'] == 'memory-heading'
    assert item['attrs']['confidence_level'] == {'value': '95', 'unit': 'percent'}
    assert item['conditions'] == [] and item['time'] is None
    assert 'unresolved' in item['interpretation_status']


def test_distinct_baseline_groups_remain_distinct_even_at_the_same_age():
    items = authored_items([row(3, {'baseline_group': g}) for g in ('normal', 'nonmemory-heading')])
    assert items[0]['roles']['baseline_group'] != items[1]['roles']['baseline_group']
    assert all(c['roles']['outcome'] == 'incident Alzheimer disease' for item in items for c in item['claims'])

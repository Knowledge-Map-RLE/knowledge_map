"""Исправление типов не разрешает выдумывать единицы, контексты и исходы."""
from copy import deepcopy
from hashlib import sha256
import pytest

from domain.article_maps import fingerprint, ArticleMapError
from domain.whole_map_context import VERSION
from domain.whole_map_forecast import project
from tests.test_schema6_prediction import graph


def audited(name='Cohens_d', value=0.18, category='dimensionless_statistic', local=False, logic='single'):
    source = graph('one', ['alpha', 'beta', 'gamma'])
    source['source'].update(text='Source statistic and study method.', content_end=34,
                           units=[{'id': 'U1', 'start': 0, 'end': 34, 'text': 'Source statistic and study method.'}])
    source['source']['sha256'] = sha256(source['source']['text'].encode()).hexdigest()
    original = source['graph']['knowledge'][0]
    original['semantic_frame']['logic'] = logic
    statement = original['semantic_frame']['statements'][0]
    statement['qualifiers']['attributes'] = [{'name': name, 'value': value, 'unit': None}]
    if local:
        statement['conditions'] = []
    entry = {'article_id': 'one', 'run_id': 'run-one', 'source_sha256': source['source']['sha256'],
             'knowledge_id': 'K1', 'knowledge_sha256': fingerprint(original), 'graph_sha256': fingerprint(source['graph']),
             'decision': 'resolve_for_pattern_analysis', 'context_resolution': 'source_local_report' if local else 'existing_scope',
             'reason_ru': 'Проверен тип по источнику.', 'reason_en': 'Source-grounded type audit.',
             'attribute_types': [{'statement_id': 'S1', 'attribute_name': name, 'type': category}],
             'evidence': [{'unit_id': 'U1', 'start': 0, 'end': 34, 'text': source['source']['text'], 'sha256': source['source']['sha256']}]}
    audit = {'version': VERSION, 'author': 'Codex', 'expert_validated': False, 'model_calls': 0, 'entries': [entry]}
    return source, audit


def test_typed_dimensionless_statistic_is_not_a_missing_physical_unit():
    source, audit = audited()
    before = deepcopy(source)
    assert not project([source])[0][('one', 'K1')]['eligible']
    record = project([source], audit)[0][('one', 'K1')]
    assert record['eligible'] and source == before
    assert record['frame']['statements'][0]['attributes'][0]['unit'] is None
    assert record['frame']['statements'][0]['attributes'][0]['value'] == '0.18'


def test_binary_codes_preserve_source_local_scope_without_inventing_date():
    source, audit = audited('long_code', 1, 'category_code', local=True)
    frame = project([source], audit)[0][('one', 'K1')]['frame']
    assert frame['statements'][0]['scope']['study_group'] == 'one'
    assert frame['statements'][0]['scope']['time'] is None
    assert frame['statements'][0]['attributes'][0]['value'] == '1'


@pytest.mark.parametrize('mutation', ['source_hash', 'graph_hash', 'knowledge_hash', 'quote', 'unrelated_unit', 'duplicate'])
def test_annotation_cannot_change_bound_sources(mutation):
    source, audit = audited()
    entry = audit['entries'][0]
    if mutation.endswith('hash'):
        entry[{'source_hash': 'source_sha256', 'graph_hash': 'graph_sha256', 'knowledge_hash': 'knowledge_sha256'}[mutation]] = 'tampered'
    elif mutation == 'quote':
        entry['evidence'][0]['text'] = 'Different quotation.'
    elif mutation == 'unrelated_unit':
        entry['evidence'][0]['unit_id'] = 'another-unit'
    else:
        audit['entries'].append(deepcopy(entry))
    with pytest.raises(ArticleMapError):
        project([source], audit)


@pytest.mark.parametrize('name,value,category', [('beta', 0.2, 'dimensionless_statistic'),
                                              ('intra_CV', 19.04, 'dimensionless_statistic'),
                                              ('long_code', 2, 'category_code')])
def test_ambiguous_units_and_invalid_category_values_are_rejected(name, value, category):
    source, audit = audited(name, value, category)
    with pytest.raises(ArticleMapError):
        project([source], audit)


def test_retained_unknown_context_is_not_silently_repaired():
    source, audit = audited(local=True)
    audit['entries'][0]['decision'] = 'retain_unknown'
    assert not project([source], audit)[0][('one', 'K1')]['eligible']


def test_compound_logic_and_conflicting_numbers_survive_type_audit():
    source, audit = audited('incremental_R2', 0.168, logic='contrast')
    original = source['graph']['knowledge'][0]
    other = deepcopy(original['semantic_frame']['statements'][0])
    other['statement_id'] = 'S1-other'
    other['qualifiers']['attributes'][0]['value'] = 0.174
    original['semantic_frame']['statements'].append(other)
    entry = audit['entries'][0]
    entry['knowledge_sha256'] = fingerprint(original)
    entry['graph_sha256'] = fingerprint(source['graph'])
    entry['attribute_types'].append({**entry['attribute_types'][0], 'statement_id': 'S1-other'})
    record = project([source], audit)[0][('one', 'K1')]
    assert record['eligible'] and record['frame']['logic'] == 'contrast'
    assert [s['attributes'][0]['value'] for s in record['frame']['statements']] == ['0.168', '0.174']

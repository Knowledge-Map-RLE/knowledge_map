"""Защита допуска от будущих поправок, аннотаций, неизвестных условий и ложной независимости."""
from copy import deepcopy
import pytest
from domain.article_maps import digest
from domain.methodological_source_screening import FIELDS, screen_source_analysis
from application.methodological_source_screening import AuditMethodologicalSources


@pytest.fixture
def example():
    text = 'Methods: baseline plasma IL-6, age 70+, no dementia, global change over three years. 🧠'
    source = {'text': text, 'sha256': digest(text)}
    span = {'start': 0, 'end': len(text), 'text': text, 'offset_encoding': 'unicode_code_points'}
    values = dict.fromkeys(FIELDS, True)
    values.update(matrix='plasma', minimum_age=70, followup_years=3)
    record = {'id': 'analysis1', 'article_id': 'source1', 'family': 'family1', 'source_kind': 'full_primary_article',
              'source_sha256': source['sha256'], 'publication_date': '2012-02-24',
              'facts': {k: {'value': v, 'evidence': [deepcopy(span)]} for k, v in values.items()},
              'note_ru': 'Синтетическая проверка.', 'note_en': 'Synthetic check.'}
    return record, source


def test_eligibility_does_not_license_prediction(example):
    record, source = example; original = deepcopy(example)
    result = screen_source_analysis(record, source, '2016-06-01')
    assert result['status'] == 'eligible'
    assert not result['empirical_transfer_licensed'] and not result['training_support_added']
    assert example == original


@pytest.mark.parametrize('field', ['predictors_available_at_origin', 'adjustments_available_at_origin', 'global_change', 'baseline_il6', 'isolated_il6', 'dementia_excluded'])
def test_post_origin_and_wrong_analysis_block_admission(example, field):
    r, s = example; r['facts'][field]['value'] = False
    assert screen_source_analysis(r, s, '2016-06-01')['status'] == 'ineligible'


@pytest.mark.parametrize('field', FIELDS)
def test_unknown_not_imputed(example, field):
    r, s = example; r['facts'][field]['value'] = None
    result = screen_source_analysis(r, s, '2016-06-01')
    assert result['status'] == 'unresolved' and not result['eligible_for_frozen_question']


def test_abstract_cannot_supply_training_even_with_positive_facts(example):
    r, s = example; r['source_kind'] = 'primary_abstract'
    assert screen_source_analysis(r, s, '2016-06-01')['status'] == 'unresolved'


@pytest.mark.parametrize('field,value', [('minimum_age', 59), ('followup_years', 1), ('matrix', 'serum')])
def test_core_minimum(example, field, value):
    r, s = example; r['facts'][field]['value'] = value
    assert screen_source_analysis(r, s, '2016-06-01')['status'] == 'ineligible'


@pytest.mark.parametrize('value', [float('nan'), float('inf'), True, -1])
def test_invalid_numeric_rejected(example, value):
    r, s = example; r['facts']['minimum_age']['value'] = value
    with pytest.raises(ValueError): screen_source_analysis(r, s, '2016-06-01')


def test_publication_boundary_and_codepoint_integrity(example):
    r, s = example; r['publication_date'] = '2016-06-01'
    assert screen_source_analysis(r, s, '2016-06-01')['status'] == 'ineligible'
    r['facts']['matrix']['evidence'][0]['end'] += 1
    with pytest.raises(ValueError): screen_source_analysis(r, s, '2016-06-01')


@pytest.mark.parametrize('heading', ['References', 'BIBLIOGRAPHY', '  Bibliography  ', '6. References', '6.0. BIBLIOGRAPHY'])
def test_bibliography_cannot_supply_own_methods(example, heading):
    r, s = example; s['text'] += '\n' + heading + '\nOther study: plasma IL-6.'
    s['sha256'] = digest(s['text']); r['source_sha256'] = s['sha256']
    start = s['text'].index('Other study')
    r['facts']['matrix']['evidence'] = [{'start': start, 'end': len(s['text']), 'text': s['text'][start:], 'offset_encoding': 'unicode_code_points'}]
    with pytest.raises(ValueError): screen_source_analysis(r, s, '2016-06-01')


@pytest.mark.parametrize('published,admitted', [('2016-06-01', True), ('2023-12-31', True), ('2024-01-01', False)])
def test_explicit_extended_publication_window(example, published, admitted):
    r, s = example; r['publication_date'] = published
    assert screen_source_analysis(r, s, '2024-01-01')['eligible_for_frozen_question'] is admitted
    # Новый временной срез не меняет границу прежнего опыта.
    assert not screen_source_analysis(r, s, '2016-06-01')['eligible_for_frozen_question']


def test_family_support_not_counted_twice_and_store_is_idempotent(example):
    r, s = example; r2 = deepcopy(r); r2['id'] = 'analysis2'
    class Store:
        def __init__(self): self.rows = {}
        def audit(self, ident, row):
            if ident in self.rows: assert self.rows[ident] == row
            self.rows[ident] = deepcopy(row)
    store = Store(); app = AuditMethodologicalSources(store)
    result = app.execute([r, r2], {'source1': s}, '2016-06-01')
    assert result['eligible_analyses'] == 2 and result['eligible_independent_families'] == ['family1']
    assert app.execute([r, r2], {'source1': s}, '2016-06-01') == result
    with pytest.raises(ValueError): app.execute([r, r], {'source1': s}, '2016-06-01')

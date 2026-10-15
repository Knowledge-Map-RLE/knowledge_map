"""Кванторы, границы, часы и эпизоды проверяются без клинической экстраполяции."""
from copy import deepcopy

import pytest

from domain.article_maps import ArticleMapError
from domain.forecast_temporal_scope import compare_temporal, validate_contract, infer_assessed_existence


def contract(start='1', end='28', quantifier='some_assessed_time'):
    return {'anchor': 'EAE onset', 'unit': 'day', 'episode': 'initial_course', 'time_quantifier': quantifier,
        'window': {'start': start, 'end': end, 'start_inclusive': True, 'end_inclusive': True},
        'bindings': {'population': 'group A', 'intervention': 'drug A', 'challenge': 'EAE',
            'comparator': 'control IgG', 'measurement': 'clinical score', 'aggregate': 'group mean'}}


def observed(c=None, direction='lower', precision='exact'):
    value = c or contract('3', '3', 'specified_time')
    return {'id': 'observed', 'contract': value,
        'direction': direction, 'precision': precision, 'evidence': ['explicit source quote'],
        'assessment_times': [value['window']['start']] if value['time_quantifier'] == 'specified_time' and precision == 'exact' else []}


def test_missing_old_contract_never_acquires_observed_endpoint():
    assert compare_temporal(None, [observed()], 'lower')['status'] == 'missing_prediction_temporal_contract'


def test_one_point_supports_existential_but_not_whole_window():
    row = observed()
    assert compare_temporal(contract(), [row], 'lower')['supported']
    assert not compare_temporal(contract(quantifier='all_assessed_times'), [row], 'lower')['supported']
    assert not compare_temporal(contract(quantifier='continuous_interval'), [row], 'lower')['supported']


def test_one_opposite_point_refutes_universal_but_not_existential():
    row = observed(direction='higher')
    assert compare_temporal(contract(quantifier='all_assessed_times'), [row], 'lower')['contradicted']
    assert compare_temporal(contract(quantifier='continuous_interval'), [row], 'lower')['contradicted']
    assert not compare_temporal(contract(), [row], 'lower')['contradicted']


def test_opposite_whole_assessed_window_can_refute_existential():
    assert compare_temporal(contract(), [observed(contract(quantifier='all_assessed_times'), 'higher')], 'lower')['contradicted']


@pytest.mark.parametrize('quantifier', ['some_assessed_time', 'all_assessed_times', 'continuous_interval'])
def test_continuous_evidence_preserves_quantifier(quantifier):
    result = compare_temporal(contract(quantifier=quantifier), [observed(contract(quantifier='continuous_interval'))], 'lower')
    assert result['supported'] and not result['scientific_confirmation']


def test_assessed_interval_cannot_become_continuous_effect():
    result = compare_temporal(contract(quantifier='continuous_interval'), [observed(contract(quantifier='all_assessed_times'))], 'lower')
    assert not result['supported']


@pytest.mark.parametrize('field', ['anchor', 'episode', 'population', 'intervention', 'challenge', 'comparator', 'measurement', 'aggregate'])
def test_other_clock_or_context_is_not_the_same_result(field):
    row = observed()
    if field in ('anchor', 'episode'): row['contract'][field] = 'other'
    else: row['contract']['bindings'][field] = 'other'
    result = compare_temporal(contract(), [row], 'lower')
    assert result['excluded_context_ids'] == ['observed'] and not result['supported'] and not result['contradicted']


@pytest.mark.parametrize('direction,precision', [('not_detected', 'exact'), ('unreported', 'exact'), ('lower', 'approximate')])
def test_uncertainty_never_becomes_zero_effect_or_exact_endpoint(direction, precision):
    row = observed(direction=direction, precision=precision)
    result = compare_temporal(contract(), [row], 'lower')
    assert result['uncertain_observation_ids'] == ['observed'] and not result['supported'] and not result['contradicted']


def test_open_boundary_unit_conversion_and_input_preservation():
    claim = contract('1', '2'); row = observed(contract('24', '24', 'specified_time'))
    row['contract']['unit'] = 'hour'; before = deepcopy((claim, row))
    assert compare_temporal(claim, [row], 'lower')['supported']
    claim['window']['start_inclusive'] = False
    assert not compare_temporal(claim, [row], 'lower')['supported']
    assert row == before[1]


def test_conflicting_qualifying_evidence_is_explicit():
    rows = [observed(contract(quantifier='all_assessed_times')), observed(direction='higher')]
    rows[1]['id'] = 'opposite-point'
    result = compare_temporal(contract(quantifier='all_assessed_times'), rows, 'lower')
    assert result['status'] == 'conflicting_temporal_evidence' and not result['supported'] and not result['contradicted']


@pytest.mark.parametrize('change', ['nan', 'numeric', 'reversed', 'empty', 'calendar_month', 'unknown_quantifier', 'extra', 'nonpoint'])
def test_invalid_temporal_contracts_fail_atomically(change):
    value = contract()
    if change == 'nan': value['window']['end'] = 'NaN'
    elif change == 'numeric': value['window']['end'] = 28
    elif change == 'reversed': value['window']['end'] = '0'
    elif change == 'empty': value['window'].update(end='1', start_inclusive=False)
    elif change == 'calendar_month': value['unit'] = 'month'
    elif change == 'unknown_quantifier': value['time_quantifier'] = 'always'
    elif change == 'extra': value['result'] = 'forbidden'
    elif change == 'nonpoint': value['time_quantifier'] = 'specified_time'
    with pytest.raises(ArticleMapError): validate_contract(value)


def test_source_temporal_deduction_requires_explicit_clinical_window_not_histology_end():
    value = contract('3', '3', 'specified_time')
    value.update(anchor='EAE disease onset', episode='initial_four_dose_course')
    value['bindings'].update(measurement='ordinal_eae_clinical_score', aggregate='reported_group_comparison')
    row = observed(value)
    roles = [{'role': r, 'value': value['bindings'][r]} for r in ('population', 'intervention', 'challenge', 'comparator')]
    receiver = {'body': [
        {'key': ['study', 'method'], 'frame': {'statements': [{'roles': roles,
            'attributes': [{'name': 'EAE-relative days', 'value': '1; 4; 8; 12', 'unit': 'day'}]}]}},
        {'key': ['study', 'measurement'], 'frame': {'statements': [{'attributes': [
            {'name': 'explicit clinical observation end', 'value': '28', 'unit': 'day after EAE onset'},
            {'name': 'histopathology endpoint, separate measure', 'value': '85', 'unit': 'day after EAE onset'}]}]}}]}
    result = infer_assessed_existence(receiver, [row], 'lower')
    assert len(result['consequences']) == 1
    consequence = result['consequences'][0]
    assert consequence['contract']['window'] == {'start': '1', 'end': '28', 'start_inclusive': True, 'end_inclusive': True}
    assert not consequence['is_future_prediction'] and not consequence['is_new_scientific_fact']
    receiver['body'][1]['frame']['statements'][0]['attributes'][0]['value'] = None
    assert infer_assessed_existence(receiver, [row], 'lower')['consequences'] == []
    receiver['body'][1]['frame']['statements'][0]['attributes'][0]['value'] = '28'
    row['precision'] = 'approximate'
    assert infer_assessed_existence(receiver, [row], 'lower')['consequences'] == []


def test_sampled_universal_does_not_create_existence_or_interpolate_an_unmeasured_time():
    row = observed(contract('1', '3', 'all_assessed_times'))
    assert not compare_temporal(contract('1', '3'), [row], 'lower')['supported']
    row['assessment_times'] = ['1', '3']
    assert compare_temporal(contract('1', '3'), [row], 'lower')['supported']
    assert not compare_temporal(contract('2', '2', 'specified_time'), [row], 'lower')['supported']
    assert compare_temporal(contract('3', '3', 'specified_time'), [row], 'lower')['supported']
    row['direction'] = 'higher'
    assert not compare_temporal(contract('1.4', '1.6', 'continuous_interval'), [row], 'lower')['contradicted']
    assert compare_temporal(contract('1', '3', 'all_assessed_times'), [row], 'lower')['contradicted']

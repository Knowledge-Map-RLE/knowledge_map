"""Числовое следствие не подменяет научный прогноз или значимость."""
from copy import deepcopy
from decimal import Decimal
import pytest

from domain.article_maps import fingerprint
from domain.whole_map_numeric import number, p_bound, statistical_finding, signed_statistic, ordered_pair, project_numeric, interval_diagnostic


def statement(value='−.418', predicate='stratified correlation', name='r'):
    return {'predicate': predicate, 'roles': [{'role': 'predictor', 'value': 'vegetable intake', 'reference_kind': 'concept'},
        {'role': 'outcome', 'value': 'plasma marker', 'reference_kind': 'concept'},
        {'role': 'population', 'value': 'study participants', 'reference_kind': 'concept'}],
        'scope': {'time': None, 'conditions': ['explicit study context'], 'study_group': 'source', 'quantifier': None, 'modality': 'reported'},
        'attributes': [{'name': name, 'value': value, 'unit': None}, {'name': 'p', 'value': '.3', 'unit': None}], 'negated': False}


def contrast():
    first = statement('1.14', 'group comparison', 'value')
    first['roles'] = [{'role': 'measure', 'value': 'cereal intake', 'reference_kind': 'concept'},
                      {'role': 'population', 'value': 'CNI study participants', 'reference_kind': 'concept'}]
    first['attributes'][0]['unit'] = 'servings/day'
    second = deepcopy(first)
    second['roles'][1]['value'] = 'MCI study participants'
    second['attributes'][0]['value'] = '.73'
    return {'kind': 'state', 'action_status': None, 'logic': 'contrast', 'statements': [first, second]}


@pytest.mark.parametrize('value', ['<.001', '.001 2', '0.4 ± 0.2', '(−0.2 to 0.1)', 'NaN', 'Infinity', True])
def test_only_explicit_finite_point_estimates_are_parsed(value):
    assert number(value) is None


def test_unicode_minus_and_rounded_zero_preserve_numeric_direction():
    assert number('−.418') == Decimal('-.418')
    result, error = signed_statistic(statement())
    assert error is None and result['statement']['attributes'][0]['value'] == 'below_null'
    assert not result['forecast_eligible'] and not result['biological_direction_established']
    zero, _ = signed_statistic(statement('-0.000'))
    assert zero['statement']['attributes'][0]['value'] == 'at_null'
    assert zero['statement']['attributes'][1]['value'] != 'no association'


@pytest.mark.parametrize('p,alpha,result', [('.04', '.017', 'not_detected_at_declared_threshold'),
    ('.04', '.05', 'detected_at_declared_threshold'), ('<.01', '.017', 'detected_at_declared_threshold'),
    ('<.017', '.017', 'detected_at_declared_threshold'), ('<=.017', '.017', 'not_established'),
    ('>.04', '.05', 'not_established'), ('.001 2', '.017', 'not_established'), ('.001', None, 'not_established')])
def test_significance_requires_a_declared_threshold_and_unambiguous_p(p, alpha, result):
    assert statistical_finding(p, alpha) == result


def test_negative_slope_does_not_guess_binary_exposure_coding():
    view, _ = signed_statistic(statement('−.538', 'regression coefficient', 'b'))
    assert not view['forecast_eligible']
    assert 'numeric axes only' in view['statement']['attributes'][1]['value']
    assert view['statistical_finding'] == 'not_established'


def test_intercept_cannot_be_used_as_an_exposure_association():
    s = statement('0.595', 'regression coefficient', 'b')
    s['roles'][0]['value'] = 'regression intercept'
    assert signed_statistic(s)[1] == 'intercept_is_not_exposure_effect'


def test_ratio_null_is_unity_and_is_not_causal():
    s = statement('1.12', 'hazard ratio', 'estimate')
    view, error = signed_statistic(s)
    assert error is None and view['null'] == '1' and view['statement']['attributes'][0]['value'] == 'above_null'
    assert not view['forecast_eligible']
    s['attributes'][0]['value'] = '0'
    assert signed_statistic(s)[1] == 'nonpositive_ratio'


def test_group_order_keeps_compound_logic_and_does_not_infer_population_difference():
    original = contrast()
    before = deepcopy(original)
    view, error = ordered_pair(original)
    assert error is None and original == before
    assert view['frame']['logic'] == 'contrast'
    assert [s['attributes'][1]['value'] for s in view['frame']['statements']] == ['higher', 'lower']
    assert all(s['attributes'][2]['value'] == 'not asserted' for s in view['frame']['statements'])
    assert view['statistical_finding'] == 'not_established'


@pytest.mark.parametrize('case', ['unit', 'time', 'measure', 'negation', 'p', 'third_statement', 'argument'])
def test_incompatible_or_compound_comparisons_are_not_selectively_simplified(case):
    frame = contrast()
    second = frame['statements'][1]
    if case == 'unit': second['attributes'][0]['unit'] = 'servings/week'
    elif case == 'time': second['scope']['time'] = 'different period'
    elif case == 'measure': second['roles'][0]['value'] = 'red meat intake'
    elif case == 'negation': second['negated'] = True
    elif case == 'p': second['attributes'][1]['value'] = '.01'
    elif case == 'third_statement': frame['statements'].append(deepcopy(second))
    else: frame['logic'] = 'argument'
    assert ordered_pair(frame)[0] is None


def test_signed_compound_block_with_unsupported_member_is_retained_whole():
    frame = {'kind': 'state', 'action_status': None, 'logic': 'argument', 'statements': [statement(), statement(predicate='causes')]}
    record = {'key': ('source', 'K1'), 'frame': frame, 'text': 'Full author argument', 'run_id': 'run',
              'eligible': True, 'provenance': [{'unit_ids': ['U1']}, {'unit_ids': ['U2']}]}
    output, diagnostic = project_numeric({record['key']: record})
    assert not diagnostic['proofs'] and output[record['key']]['frame'] == frame


def test_numeric_proof_retains_every_original_number_and_source_constraint():
    frame = contrast()
    record = {'key': ('source', 'K1'), 'frame': frame, 'text': 'Full source comparison', 'run_id': 'run',
              'eligible': True, 'provenance': [{'unit_ids': ['U1']}]}
    before = deepcopy(record)
    output, diagnostic = project_numeric({record['key']: record})
    proof = diagnostic['proofs'][0]
    assert proof['parent_frame'] == before['frame'] and proof['parent_frame_sha256'] == fingerprint(before['frame'])
    assert proof['parent_frame']['statements'][0]['attributes'][0]['value'] == '1.14'
    assert record == before and output[record['key']]['frame'] != before['frame']
    assert proof['provenance'] == before['provenance'] and not proof['new_empirical_measurement']


def test_interval_diagnostic_does_not_rewrite_estimate_or_assume_interval_method():
    assert interval_diagnostic('(−0.077 to 0.282)', Decimal('-.102')) == 'reported_point_outside_interval'
    assert interval_diagnostic('(0.2 to -0.1)', Decimal('.1')) == 'reported_interval_bounds_reversed'
    assert interval_diagnostic(None, Decimal('.1')) == 'not_reported'


def test_explicit_threshold_is_used_without_silently_stripping_table_footnotes():
    s = statement('−.102', 'regression coefficient', 'b')
    s['attributes'].append({'name': 'bonferroni p', 'value': '<.017', 'unit': None})
    s['attributes'][1]['value'] = '.3'
    assert signed_statistic(s)[0]['statistical_finding'] == 'not_detected_at_declared_threshold'
    s['attributes'][1]['name'] = 'p and annotation'
    s['attributes'][1]['value'] = '.001 2'
    assert signed_statistic(s)[0]['statistical_finding'] == 'not_established'

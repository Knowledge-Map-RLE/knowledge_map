"""Качественные следствия чисел сохраняют родителя и не являются новым измерением."""
from copy import deepcopy
from decimal import Decimal
import re

from domain.article_maps import fingerprint
from domain.statistical_context_views import project_audited_frame
from domain.statistical_model_views import project_frame as project_model_frame
from domain.statistical_primitives import number, p_bound, statistical_finding, interval_diagnostic, attributes, roles, direction

VERSION = 'whole-map-numeric-consequences-4'
FOUNDATION = {
    'correlation': 'https://www.itl.nist.gov/div898/software/dataplot/refman2/auxillar/correlat.htm',
    'linear_coefficient': 'https://www.itl.nist.gov/div898/handbook/pmd/section1/pmd141.htm',
    'ordered_estimates': 'Exact decimal order on two reported estimates of the same measure and unit; not a population test',
    'typed_models': 'Conditional fitted direction under explicit model, positive exposure increment, units, estimand and declared test threshold; full parent retained',
    'ratio': 'Order of an explicitly typed positive reported ratio relative to unity; exposure contrast and causality are not inferred',
}
CORRELATIONS = {'partial correlation', 'stratified correlation', 'correlation coefficient'}
RATIOS = {'hazard ratio', 'risk ratio', 'odds ratio'}


def signed_statistic(statement):
    attr, role = attributes(statement), roles(statement)
    if attr is None or role is None:
        return None, 'ambiguous_attribute_or_role'
    predicate = statement['predicate']
    if predicate in CORRELATIONS:
        kind, name, null = 'correlation', 'r', Decimal(0)
    elif predicate == 'regression coefficient':
        kind, name, null = 'linear_coefficient', 'b', Decimal(0)
    elif predicate in RATIOS:
        kind, name, null = 'ratio', 'estimate', Decimal(1)
    else:
        return None, 'no_signed_statistic_operator'
    if not {'outcome'} <= role.keys() or not ({'predictor', 'exposure'} & role.keys()):
        return None, 'statistic_axes_missing'
    if any(isinstance(v, dict) for v in role.values()):
        return None, 'nested_axes_require_explicit_interpretation'
    if role.get('predictor') == 'regression intercept':
        return None, 'intercept_is_not_exposure_effect'
    point = number(attr.get(name, {}).get('value'))
    if point is None:
        return None, 'nonpoint_or_ambiguous_estimate'
    if kind == 'correlation' and not Decimal(-1) <= point <= Decimal(1):
        return None, 'correlation_out_of_range'
    if kind == 'ratio' and point <= 0:
        return None, 'nonpositive_ratio'
    declared = p_bound(attr.get('bonferroni p', {}).get('value'))
    alpha = str(declared[1]) if declared and declared[0] == '<' else None
    finding = statistical_finding(attr.get('p', attr.get('p and annotation', {})).get('value'), alpha)
    result = deepcopy(statement)
    result['predicate'] = 'reported ' + kind.replace('_', ' ') + ' direction'
    result['attributes'] = [{'name': 'reported estimate direction', 'value': direction(point, null), 'unit': None},
                            {'name': 'interpretation', 'value': 'numeric axes only; exposure encoding not established', 'unit': None}]
    result.pop('attribute_types', None)
    return {'statement': result, 'operator': kind, 'point': str(point), 'null': str(null),
            'biological_direction_established': False, 'forecast_eligible': False,
            'interval_diagnostic': interval_diagnostic(attr.get('ci95', {}).get('value'), point),
            'statistical_finding': finding, 'declared_alpha': alpha,
            'finding_basis': 'conditional comparison of reported rounded p and explicit strict threshold; no footnote stripping',
            'reason': 'explicit_exposure_encoding_and_model_basis_required'}, None


def ordered_pair(frame):
    if frame['logic'] != 'contrast' or len(frame['statements']) != 2:
        return None, 'not_a_two_statement_contrast'
    first, second = frame['statements']
    if first['predicate'] != 'group comparison' or second['predicate'] != first['predicate']:
        return None, 'no_group_estimate_order_operator'
    a, b = attributes(first), attributes(second)
    ra, rb = roles(first), roles(second)
    if any(v is None for v in (a, b, ra, rb)):
        return None, 'ambiguous_attribute_or_role'
    if any(isinstance(v, dict) for r in (ra, rb) for v in r.values()):
        return None, 'nested_comparison_roles'
    if not {'measure', 'population'} <= ra.keys() or set(ra) != set(rb):
        return None, 'comparison_axes_missing'
    if ra['population'] == rb['population'] or any(ra[k] != rb[k] for k in ra if k != 'population'):
        return None, 'different_measures_or_identical_groups'
    if any(first[k] != second[k] for k in ('scope', 'negated')) or first['negated']:
        return None, 'different_scope_or_negated_comparison'
    left, right = a.get('value'), b.get('value')
    if left is None or right is None or left['unit'] is None or left['unit'] != right['unit']:
        return None, 'comparison_units_unknown_or_different'
    x, y = number(left['value']), number(right['value'])
    if x is None or y is None:
        return None, 'nonpoint_or_ambiguous_comparison'
    if a.get('p') != b.get('p'):
        return None, 'inconsistent_reported_comparison_test'
    transformed = deepcopy(frame)
    for index, statement in enumerate(transformed['statements']):
        delta = x - y if index == 0 else y - x
        statement['predicate'] = 'reported group estimate order'
        statement['attributes'] = [{'name': 'measure unit', 'value': left['unit'], 'unit': None},
            {'name': 'reported pair order', 'value': 'higher' if delta > 0 else 'lower' if delta < 0 else 'equal', 'unit': None},
            {'name': 'population inference', 'value': 'not asserted', 'unit': None}]
        statement.pop('attribute_types', None)
    return {'frame': transformed, 'operator': 'ordered_estimates', 'forecast_eligible': True,
            'statistical_finding': 'not_established', 'biological_direction_established': False,
            'reason': 'reported_estimate_order_only; population_difference_or_significance_not_asserted'}, None


def project_numeric(records):
    output, coverage, proofs = deepcopy(records), [], []
    for key, parent in records.items():
        frame = parent['frame']
        if not parent['eligible']:
            coverage.append({'key': key, 'status': 'ineligible_parent_context'})
            continue
        view, audited_reason = project_audited_frame(frame, parent.get('model_context'))
        model_reason = None
        if view is None:
            view, model_reason = project_model_frame(frame)
        pair_reason = None
        if view is None:
            view, pair_reason = ordered_pair(frame)
        if view is None:
            parts, failure = [], None
            for s in frame['statements']:
                part, error = signed_statistic(s)
                if part is None:
                    failure = error
                    break
                parts.append(part)
            # Все части аргумента/противопоставления сохраняются вместе, без выборочного допуска.
            if failure is None and parts:
                view = {'frame': {**deepcopy(frame), 'statements': [p['statement'] for p in parts]},
                        'operator': 'signed_statistics', 'forecast_eligible': False,
                        'statements': [{k: v for k, v in p.items() if k != 'statement'} for p in parts],
                        'reason': 'exposure_encoding_not_established_for_content_transfer'}
            else:
                coverage.append({'key': key, 'status': 'no_applicable_numeric_operator',
                                 'audited_model_reason': audited_reason, 'model_reason': model_reason, 'pair_reason': pair_reason, 'statement_reason': failure})
                continue
        proof = {'id': fingerprint({'version': VERSION, 'key': key, 'parent': frame, 'view': view}),
                 'key': key, 'run_id': parent['run_id'], 'parent_frame_sha256': fingerprint(frame),
                 'parent_frame': deepcopy(frame), 'source_text': parent['text'], 'provenance': parent['provenance'],
                 **view, 'logical_entailment': 'conditional_numeric_consequence_only',
                 'new_empirical_measurement': False, 'causality_asserted': False, 'expert_validated': False}
        proofs.append(proof)
        coverage.append({'key': key, 'status': 'qualitative_view_admitted' if view['forecast_eligible'] else 'numeric_consequence_only',
                         'proof_id': proof['id'], 'operator': view['operator'], 'reason': view['reason']})
        if view['forecast_eligible']:
            output[key]['frame'] = view['frame']
            output[key]['numeric_proof_id'] = proof['id']
    return output, {'version': VERSION, 'foundation': FOUNDATION, 'coverage': coverage, 'proofs': proofs,
                    'model_calls': 0, 'new_empirical_measurements': 0}

"""Разность двух общереферентных контрастов: числовое следствие полного модельного блока."""
from collections import Counter, defaultdict
from copy import deepcopy
from decimal import localcontext
from itertools import combinations

from domain.article_maps import fingerprint, require
from domain.comparison_normalization import normalize
from domain.evidence_origin_audit import validate_origins
from domain.statistical_context_audit import audit_models
from domain.statistical_context_views import project_audited_frame
from domain.statistical_primitives import attributes, roles, number
from domain.whole_map_forecast import project

VERSION = 'closed-shared-reference-contrast-composition-1'
LIMITS = {'pair_steps': 200000}
FOUNDATION = {
    'equation': '(B - R) - (A - R) = B - A',
    'qualification_ru': 'Относится к одной и той же явно заданной шкале и модели; это арифметика напечатанных коэффициентов.',
    'variance_equation': 'Var(bB-bA) = Var(bB) + Var(bA) - 2*Cov(bA,bB)',
    'uncertainty_ru': 'Без ковариации и совместного распределения новый интервал, p и значимость не выводятся.',
}


def exact_difference(left, right):
    values = [number(left), number(right)]
    require(all(v is not None for v in values), 'Finite decimal operands required')
    tuples = [v.as_tuple() for v in values]
    minimum = min(t.exponent for t in tuples)
    precision = max(len(t.digits) + t.exponent - minimum for t in tuples) + 1
    require(precision <= 10000 and all(abs(t.exponent) <= 10000 for t in tuples),
            'Decimal contrast precision budget exceeded; no partial result')
    with localcontext() as context:
        context.prec = max(precision, 1)
        return values[1] - values[0]


def proof_graph(key, first, second, reference):
    prefix = fingerprint(key)
    root = prefix + ':parent'; operator = prefix + ':operator:' + str(first['position']) + ':' + str(second['position'])
    operands = [prefix + ':position:' + str(p['position']) for p in (first, second, reference)]
    target = operator + ':conclusion'
    return {'nodes': [{'id': root, 'kind': 'complete_parent', 'native_key': list(key)},
                      *[{'id': n, 'kind': 'source_bound_parameter', 'statement_position': p['position'],
                         'independent_premise_license': False} for n, p in zip(operands, (first, second, reference))],
                      {'id': operator, 'kind': 'arithmetic_operator', 'version': VERSION},
                      {'id': target, 'kind': 'conditional_comparison'}],
            'edges': [*({'source': root, 'target': n} for n in operands),
                      *({'source': n, 'target': operator} for n in operands),
                      {'source': operator, 'target': target}],
            'joint_operand_group': operands, 'native_visible_map_modified': False}


def conclusion_frame(basis, first, second, delta):
    scope = deepcopy(basis['scope'])
    scope['conditions'] = sorted(set(scope['conditions']) | {
        'conditional on the same declared fitted model and common reference',
        'exact arithmetic of reported rounded coefficients; no new empirical measurement'})
    return {'kind': 'state', 'action_status': None, 'logic': 'single',
        'statements': [{'predicate': 'computed same-model category contrast',
            'roles': [*({'role': r, 'value': v, 'reference_kind': 'concept'} for r, v in sorted(basis['roles'].items())),
                      {'role': 'from category', 'value': first['category'], 'reference_kind': 'concept'},
                      {'role': 'to category', 'value': second['category'], 'reference_kind': 'concept'}],
            'scope': scope, 'negated': False,
            'attributes': [{'name': 'reported coefficient difference', 'value': str(delta), 'unit': basis['unit']},
                {'name': 'model', 'value': basis['model'], 'unit': None},
                {'name': 'estimand', 'value': basis['estimand'], 'unit': None},
                {'name': 'reference category', 'value': basis['reference'], 'unit': None},
                {'name': 'statistical finding', 'value': 'not_established', 'unit': None},
                {'name': 'derivation status', 'value': 'conditional reported parameter consequence', 'unit': None}]}]}


def extract_parameter_group(record, audit):
    frame = record['frame']
    if not record['eligible']: return None, 'unknown_parent_context'
    if audit is None: return None, 'model_context_not_audited'
    if frame['logic'] not in {'contrast', 'conjunction'}: return None, 'closed_compound_model_required'
    if any(c['kind'] not in {'category_coefficient', 'reference_coefficient'} for c in audit['statements']):
        return None, 'not_a_categorical_reference_parameter_block'
    licensed, reason = project_audited_frame(frame, audit)
    if licensed is None: return None, reason
    groups = defaultdict(list)
    for i, (statement, context, evaluated) in enumerate(zip(frame['statements'], audit['statements'], licensed['statements'])):
        a, r = attributes(statement), roles(statement)
        if a is None or r is None: return None, 'ambiguous_model_parameter'
        if not {'cohort', 'exposure', 'outcome', 'adjustment', 'category'} <= set(r):
            return None, 'complete_parameter_axes_required'
        if 'source table' not in a: return None, 'explicit_parameter_table_required'
        if context['reference'] is None: return None, 'explicit_reference_required'
        basis = {'roles': {k: v for k, v in r.items() if k != 'category'},
            'scope': deepcopy(statement['scope']), 'model': context['model'], 'unit': context['unit'],
            'estimand': context['estimand'], 'bounds': context['bounds'], 'threshold': context['threshold'],
            'reference': normalize(context['reference']), 'analysis_n': evaluated['analysis_n'],
            'source_table': deepcopy(a['source table']),
            'model_evidence_unit_ids': sorted(context['evidence_unit_ids'])}
        point = number(evaluated['point']) if evaluated['point'] is not None else None
        is_reference = context['kind'] == 'reference_coefficient'
        require((point is None) == is_reference, 'Parameter point disagrees with explicit reference status')
        groups[fingerprint(basis)].append({'position': i, 'category': r['category'], 'point': str(point) if point is not None else None,
            'is_reference': is_reference, 'basis': basis, 'native_statement_id': record['native_knowledge']['semantic_frame']['statements'][i]['statement_id']})
    # Ни одна часть родителя не опускается: ошибочная модель отклоняет весь блок.
    for group in groups.values():
        if len({p['category'] for p in group}) != len(group): return None, 'repeated_category_in_model'
        reference = [p for p in group if p['is_reference']]
        if len(reference) != 1 or reference[0]['category'] != group[0]['basis']['reference']:
            return None, 'complete_unique_reference_in_each_model_required'
    return list(groups.values()), None


def compose_model_contrasts(maps, context_audit, model_audit, origin_audit):
    origins = validate_origins(maps, origin_audit)
    require(origins is not None, 'Complete contrast origin audit required')
    native = {(m['article_id'], k['knowledge_id']): k for m in maps for k in m['graph']['knowledge']}
    records, _, _ = project(maps, context_audit)
    audits = audit_models(maps, model_audit)
    coverage = []; counts = Counter(); results = []; steps = 0
    for key, record in sorted(records.items()):
        require(key in native, 'Contrast native parent missing')
        record['native_knowledge'] = native[key]
        groups, reason = extract_parameter_group(record, audits.get(key))
        if groups is None:
            counts[reason] += 1
            coverage.append({'key': list(key), 'status': reason, 'consequences': []})
            continue
        created = []
        for group in groups:
            nonreference = sorted([p for p in group if not p['is_reference']], key=lambda p: p['category'])
            reference = next(p for p in group if p['is_reference'])
            for first, second in combinations(nonreference, 2):
                steps += 1
                require(steps <= LIMITS['pair_steps'], 'Contrast composition budget exceeded; no partial result')
                delta = exact_difference(first['point'], second['point'])
                direction = 'higher_as_printed' if delta > 0 else 'lower_as_printed' if delta < 0 else 'equal_as_printed'
                proof = {'version': VERSION, 'foundation': FOUNDATION, 'parent_key': list(key), 'run_id': record['run_id'],
                    'complete_native_knowledge': deepcopy(native[key]), 'parent_knowledge_sha256': fingerprint(native[key]),
                    'complete_normalized_parent_frame': deepcopy(record['frame']),
                    'complete_parent_provenance': deepcopy(record['provenance']),
                    'complete_model_audit': deepcopy(audits[key]), 'origin': deepcopy(origins['knowledge'][key]),
                    'selected_positions': [first['position'], second['position']], 'reference_position': reference['position'],
                    'all_parent_positions_retained': list(range(len(record['frame']['statements']))),
                    'parent_logic_preserved': True, 'parts_independently_asserted': False, 'conditions_removed': False,
                    'independent_replication': False, 'causality_asserted': False, 'expert_validated': False}
                result = {'status': 'conditional_model_parameter_consequence', 'basis': deepcopy(first['basis']),
                    'from_category': first['category'], 'to_category': second['category'],
                    'operand_a': first['point'], 'operand_b': second['point'], 'reported_parameter_difference': str(delta),
                    'direction': direction, 'unit': first['basis']['unit'],
                    'confidence_interval': None, 'p': None, 'statistical_finding': 'not_established',
                    'uncertainty_reason': 'joint_parameter_covariance_not_available',
                    'rounding_basis': 'exact_decimal_difference_of_printed_coefficients; unrounded_difference_not_identified',
                    'new_comparison_within_admitted_parent': True, 'future_empirical_prediction': False,
                    'transfer_to_other_model_or_population': False, 'proof': proof,
                    'proof_graph': proof_graph(key, first, second, reference),
                    'conclusion_frame': conclusion_frame(first['basis'], first, second, delta)}
                result['id'] = fingerprint(result)
                results.append(result); created.append(result['id'])
        status = 'closed_model_composition_admitted' if created else 'no_two_nonreference_categories'
        counts[status] += 1
        coverage.append({'key': list(key), 'status': status, 'consequences': created,
                         'parameter_groups': deepcopy(groups)})
    require(len(coverage) == len(records), 'Contrast coverage differs')
    # Удаление видимых зависимостей не меняет этот оператор: его основания заданы семантикой полной модели.
    return {'version': VERSION, 'limits': LIMITS, 'foundation': FOUNDATION, 'canonical_blocks': len(records),
        'native_statements': sum(len(r['frame']['statements']) for r in records.values()),
        'consequences': results, 'coverage': coverage, 'counts': dict(counts), 'pair_steps': steps,
        'ablation': {'graph': [r['id'] for r in results], 'same_semantics_without_dependencies': [r['id'] for r in results],
                    'operator_uses_visible_edges': False, 'advantage_from_visible_edges': False},
        'model_calls': 0, 'target_read': False, 'new_empirical_predictions': 0,
        'scientific_success': False, 'graph_advantage_demonstrated': False,
        'policy_ru': 'Новые сравнения напечатанных коэффициентов, условные на полном родителе; не новые измерения и не прогнозы будущих статей.'}

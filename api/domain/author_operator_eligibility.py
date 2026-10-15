"""Авторское использование знания не удостоверяет идентифицируемое правило вывода."""
from collections import Counter
from copy import deepcopy
from fractions import Fraction
from hashlib import sha256

from domain.article_maps import require, fingerprint

VERSION = 'source-bound-author-operator-eligibility-1'


def fit_counterexample(delta, intercept=False):
    d = Fraction(str(delta)); require(0 < d < 1, 'Incremental explained variance must lie inside (0,1)')
    # Независимые центрированные X, Z, E имеют единичную дисперсию.
    # Y = mu + sqrt(base)*Z +/- sqrt(d)*X + sqrt(residual)*E.
    base = (1 - d) / 2; residual = 1 - base - d
    models = []
    for sign in (1, -1):
        models.append({'intercept': '2' if not intercept or sign == 1 else '3',
                       'added_coefficient': ('+' if intercept or sign == 1 else '-') + 'sqrt(' + str(d) + ')',
                       'variance_y': str(base + d + residual), 'baseline_R2': str(base),
                       'full_R2': str(base + d), 'incremental_R2': str(d),
                       'fitted_added_variance': str(d), 'residual_variance': str(residual)})
    require(models[0]['incremental_R2'] == models[1]['incremental_R2'], 'Countermodels must share fit')
    require(models[0]['intercept'] != models[1]['intercept'] if intercept else
            models[0]['added_coefficient'] != models[1]['added_coefficient'], 'Countermodels must disagree on the requested parameter')
    return {'incremental_R2': str(d), 'models': models,
            'requested_parameter': 'intercept' if intercept else 'added_predictor_coefficient',
            'fit_alone_identifies_parameter': False, 'source_patient_data_reconstructed': False,
            'applies_to_full_source_prose': False,
            'scope_ru': 'Алгебраический свидетель недостаточности одной сводки R². Это вымышленные '
                        'модели с независимыми центрированными переменными, не реконструкция пациентов '
                        'или всех ограничений исходного текста. Два знака дают одинаковые квадраты '
                        'коэффициентов и R²; изменение среднего меняет интерсепт без изменения R².'}


def _predicates(parent):
    return {s['predicate'].casefold().replace('_', ' ') for s in parent['complete_parent']['semantic_frame']['statements']}


def audit_author_operators(source, previous_max_premises):
    graph, circuits = source['semantic_graph'], source['argument_circuits']
    require(source['model_calls'] == 0 and source['target_read'] is False
            and source['binding']['metadata']['question'] is None, 'Source-only full argument snapshot required')
    require(type(previous_max_premises) is int and previous_max_premises > 0, 'Explicit prior operator arity required')
    require(set(circuits['nodes']) == set(graph['visible_occurrences'])
            and len(graph['parents']) == circuits['canonical_blocks'], 'Complete source circuit coverage required')
    rows = []; routes = Counter(); arities = Counter(); direct = 0
    for key, group in sorted(circuits['groups'].items()):
        require(key == group['id'] == fingerprint({k: v for k, v in group.items() if k != 'id'}), 'Author group binding changed')
        head = graph['parents'][group['head']]; body = [graph['parents'][p] for p in group['premises']]
        require(group['head_occurrence'] in circuits['nodes'] and len(body) == len(group['premise_occurrences'])
                and len(set(group['premise_occurrences'])) == len(body), 'Full author group references required')
        head_node = circuits['nodes'][group['head_occurrence']]
        require(head_node['parent'] == group['head'], 'Head occurrence differs')
        for parent_key, oid in zip(group['premises'], group['premise_occurrences']):
            require(circuits['nodes'][oid]['parent'] == graph['visible_occurrences'][oid]['parent'] == parent_key,
                    'Premise occurrence differs')
        for p in [head, *body]:
            require(p['knowledge_sha256'] == fingerprint(p['complete_parent'])
                    and p['article_id'] == group['article_id'], 'Original full parent differs')
        for ref in group['evidence']:
            require(ref['source_sha256'] == head['source_sha256'] and ref['article_id'] == head['article_id']
                    and len(ref['text']) == ref['end'] - ref['start']
                    and sha256(ref['text'].encode()).hexdigest() == ref['sha256'], 'Author transition provenance differs')
        head_origins = {s['origin'] for s in head_node['origin']['statements']}
        input_origins = [{s['origin'] for s in circuits['nodes'][oid]['origin']['statements']}
                         for oid in group['premise_occurrences']]
        own_result_inputs = [p for p, origin in zip(body, input_origins)
                             if p['complete_parent']['kind'] == 'state' and 'primary_result' in origin]
        if own_result_inputs: direct += 1
        fit_only = all(_predicates(p) == {'incremental model fit'} for p in body)
        countermodels = []
        if head['complete_parent']['kind'] == 'action': route = 'task_or_procedure_not_empirical_outcome'
        elif head_origins == {'primary_result'} and _predicates(head) == {'regression coefficient'} and fit_only:
            route = 'parameter_not_identified_by_fit_summary'
            for parent in body:
                for statement in parent['complete_parent']['semantic_frame']['statements']:
                    for attribute in statement['qualifiers'].get('attributes', []):
                        if attribute['name'] == 'incremental_R2':
                            countermodels.append({'parent_knowledge_id': parent['knowledge_id'],
                                'parent_sha256': parent['knowledge_sha256'], 'statement_id': statement['statement_id'],
                                'original_attribute': deepcopy(attribute),
                                'witness': fit_counterexample(attribute['value'], 'intercept' in head['complete_parent']['display_text'].casefold())})
            require(countermodels, 'Fit-only parameter classification requires explicit numerical witness')
        elif head_origins == {'primary_result'}:
            route = 'result_synthesis_requires_operator_license' if own_result_inputs else 'new_measurement_or_analysis_required'
        elif head_origins == {'primary_interpretation'}: route = 'interpretation_not_empirical_truth_label'
        elif head_origins <= {'cited_result', 'review_result', 'parent_cohort_report'}:
            route = 'reported_or_cited_conclusion_not_independent_support'
        else: route = 'definition_background_or_mixed_origin_requires_separate_license'
        arity = len(body); routes[route] += 1; arities[arity] += 1
        rows.append({'group_id': key, 'article_id': group['article_id'], 'head': group['head'],
                     'head_knowledge_id': head['knowledge_id'], 'head_origins': sorted(head_origins),
                     'full_premises': deepcopy(group['premises']), 'premise_knowledge_ids': [p['knowledge_id'] for p in body],
                     'premise_occurrences': deepcopy(group['premise_occurrences']), 'head_occurrence': group['head_occurrence'],
                     'arity': arity, 'exceeds_previous_arity': arity > previous_max_premises,
                     'route': route, 'direct_own_result_inputs': len(own_result_inputs),
                     'countermodels': countermodels, 'transition_evidence': deepcopy(group['evidence']),
                     'automatically_licensed_empirical_rule': False,
                     'all_members_retained': True, 'alternative_groups_merged': False,
                     'deductive_rule': False, 'causal_rule': False})
    return {'version': VERSION, 'question': None, 'rows': rows, 'counts': dict(routes),
            'arity_counts': {str(k): v for k, v in sorted(arities.items())}, 'previous_max_premises': previous_max_premises,
            'groups_above_previous_arity': sum(r['exceeds_previous_arity'] for r in rows),
            'groups_with_direct_own_result': direct, 'canonical_blocks': len(graph['parents']),
            'native_statements': graph['statement_count'], 'all_author_groups_accounted': len(rows) == len(circuits['groups']),
            'automatically_licensed_empirical_rules': [], 'future_predictions': [], 'future_results_scored': 0,
            'new_confirmed_predictions': 0, 'scientific_success': False, 'graph_advantage_demonstrated': False,
            'model_calls': 0, 'target_read': False,
            'policy_ru': 'Классификация маршрутизирует обучение; она не доказывает истинность интерпретации '
                         'или переносимость результата. Все группы и все совместные члены сохранены, '
                         'без ограничения тремя входами. Разделение результата, синтеза, интерпретации '
                         'и процедуры запрещает обучать эмпирический закон на одной лишь стрелке автора.'}

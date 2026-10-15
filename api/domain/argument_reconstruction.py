"""Ограниченные семантические операции для ретроспективной проверки аргументов.

Операторы заданы вручную. Они не обучаются, не читают скрытое заключение и
не превращают использование знания в DAG в доказательство истинности.
"""
from math import isfinite

from domain.article_maps import fingerprint, require

VERSION = 'argument-reconstruction-1'
OPERATORS = {'covariate_diagnostic', 'validation_task', 'intervention_benefit', 'pathology_specificity', 'empirical_result'}
FACT_FIELDS = {'id', 'type', 'context', 'roles', 'negated', 'status', 'data', 'origin'}
DATA_FIELDS = {
    'adjustment_contrast': {'before', 'after', 'only_added_covariate', 'sample_comparability'},
    'covariate_by_exposure': {'estimate', 'ci_lower', 'ci_upper', 'p', 'unit'},
    'covariate_by_outcome': {'estimate', 'ci_lower', 'ci_upper', 'p', 'unit'},
    'validation_requirement': {'scope', 'before_generalization'},
    'observational_association': {'effect', 'estimate', 'unit'},
    'statistical_nondetection': {'effect', 'estimate', 'unit'},
    'threshold_generalization_caveat': {'scope'},
}


def _number(value):
    return type(value) in {int, float} and isfinite(value)


def validate_request(request):
    require(set(request) == {'operator', 'facts', 'joint_groups'}, 'Unexpected generator input field')
    require(request['operator'] in OPERATORS, 'Unknown explicit operator')
    require(isinstance(request['facts'], list) and isinstance(request['joint_groups'], list), 'Invalid premise lists')
    ids = set()
    for f in request['facts']:
        require(set(f) == FACT_FIELDS and f['type'] in DATA_FIELDS, 'Unknown semantic fact contract')
        require(isinstance(f['id'], str) and f['id'] and f['id'] not in ids, 'Duplicate premise')
        ids.add(f['id'])
        require(isinstance(f['context'], str) and f['context'], 'Explicit local context required')
        require(type(f['negated']) is bool and f['status'] in {'observed', 'explicit_requirement', 'reported_caveat'}, 'Invalid fact status')
        require(isinstance(f['roles'], dict) and all(isinstance(k, str) and isinstance(v, str) and v for k, v in f['roles'].items()), 'Invalid semantic roles')
        require(isinstance(f['origin'], dict) and set(f['origin']) == {'knowledge_id', 'statement_ids'}, 'Origin must contain only opaque references')
        require(isinstance(f['origin']['knowledge_id'], str) and isinstance(f['origin']['statement_ids'], list)
                and f['origin']['statement_ids'] and all(isinstance(s, str) and s for s in f['origin']['statement_ids']), 'Invalid source references')
        require(set(f['data']) == DATA_FIELDS[f['type']], 'Unexpected semantic data field')
        d = f['data']
        if f['type'] == 'adjustment_contrast':
            for key in ['before', 'after']:
                m = d[key]
                require(set(m) == {'estimate', 'ci_lower', 'ci_upper', 'p', 'unit'}, 'Invalid adjustment measurement')
                _validate_measurement(m)
            require(type(d['only_added_covariate']) is bool and d['sample_comparability'] in {'verified', 'not_reported'}, 'Invalid adjustment comparability')
        if f['type'] in {'covariate_by_exposure', 'covariate_by_outcome'}:
            _validate_measurement(d)
        if f['type'] in {'observational_association', 'statistical_nondetection'}:
            require(_number(d['estimate']) and isinstance(d['effect'], str) and isinstance(d['unit'], str) and d['unit'], 'Invalid effect measurement')
        if f['type'] == 'validation_requirement':
            require(d['scope'] == 'independent_populations' and type(d['before_generalization']) is bool, 'Unknown validation requirement')
        if f['type'] == 'threshold_generalization_caveat':
            require(d['scope'] == 'threshold_to_continuous', 'Unknown caveat')
    for group in request['joint_groups']:
        require(isinstance(group, list) and group and len(set(group)) == len(group) and set(group) <= ids, 'Invalid joint premise group')


def _validate_measurement(m):
    require(all(_number(m[k]) for k in ['estimate', 'ci_lower', 'ci_upper', 'p']), 'Nonfinite or missing measurement')
    require(m['ci_lower'] <= m['estimate'] <= m['ci_upper'] and 0 <= m['p'] <= 1
            and isinstance(m['unit'], str) and m['unit'], 'Invalid uncertainty or unit')


def reconstruct(request):
    """На входе только разрешённые факты. Текст статьи и заключение недоступны."""
    validate_request(request)
    response = {'version': VERSION, 'request_sha256': fingerprint(request), 'operator': request['operator'],
                'status': 'abstained', 'conclusions': [], 'reasons': [], 'clinical_forecast': False,
                'rule_origin': 'handcrafted_retrospective', 'learned_rule': False, 'causal_identification': False}
    if request['operator'] == 'intervention_benefit':
        response['reasons'] = ['observational_association_does_not_identify_intervention_effect']
        return response
    if request['operator'] == 'pathology_specificity':
        response['reasons'] = ['continuous_nondetection_does_not_establish_stronger_pathological_effect']
        return response
    if request['operator'] == 'empirical_result':
        response['reasons'] = ['new_empirical_measurements_unavailable_no_validated_predictive_rule']
        return response
    facts = {f['id']: f for f in request['facts']}
    failures = set()
    for ids in request['joint_groups']:
        group = [facts[i] for i in ids]
        if len({f['context'] for f in group}) != 1:
            failures.add('incompatible_context'); continue
        if any(f['negated'] for f in group):
            failures.add('negated_premise'); continue
        if request['operator'] == 'validation_task':
            if len(group) != 1 or group[0]['type'] != 'validation_requirement' or group[0]['status'] != 'explicit_requirement':
                failures.add('explicit_validation_requirement_missing'); continue
            f = group[0]
            if not f['data']['before_generalization']:
                failures.add('generalization_condition_missing'); continue
            conclusion = {'predicate': 'validate_in_independent_populations', 'kind': 'action', 'action_status': 'unresolved',
                          'roles': f['roles'], 'modality': 'proposed_task', 'negated': False, 'context': f['context'],
                          'conditions': ['before_generalization'], 'uncertainty': [], 'premises': ids}
        else:
            by_type = {f['type']: f for f in group}
            expected = {'adjustment_contrast', 'covariate_by_exposure', 'covariate_by_outcome'}
            if len(group) != 3 or set(by_type) != expected or any(f['status'] != 'observed' for f in group):
                failures.add('joint_observations_missing'); continue
            a, e, o = (by_type[k] for k in ['adjustment_contrast', 'covariate_by_exposure', 'covariate_by_outcome'])
            roles = a['roles']
            if set(roles) != {'exposure', 'outcome', 'covariate'} or e['roles'] != {'exposure': roles['exposure'], 'outcome': roles['covariate']} or o['roles'] != {'group': roles['outcome'], 'outcome': roles['covariate']}:
                failures.add('role_alignment_missing'); continue
            d, ed, od = a['data'], e['data'], o['data']
            if d['before']['unit'] != 'odds_ratio' or d['after']['unit'] != 'odds_ratio' or ed['unit'] != od['unit']:
                failures.add('incompatible_dimensions'); continue
            if not d['only_added_covariate']:
                failures.add('other_adjustments_changed'); continue
            if not (1 < d['before']['estimate'] < d['after']['estimate'] and ed['estimate'] > 0 > od['estimate']):
                failures.add('attenuation_pattern_missing'); continue
            warnings = ['not_a_causal_confounder_identification', 'odds_ratio_noncollapsibility_not_excluded']
            if d['sample_comparability'] == 'not_reported': warnings.append('identical_analytic_sample_not_verified')
            if ed['ci_lower'] <= 0 <= ed['ci_upper'] or ed['p'] >= .05: warnings.append('exposure_covariate_direction_uncertain')
            if od['ci_lower'] <= 0 <= od['ci_upper'] or od['p'] >= .05: warnings.append('outcome_covariate_direction_uncertain')
            conclusion = {'predicate': 'candidate_covariate_attenuation_pattern', 'kind': 'state', 'action_status': None,
                          'roles': roles, 'modality': 'tentative_diagnostic_hypothesis', 'negated': False,
                          'context': a['context'], 'conditions': ['same_local_cohort', 'observational_models'],
                          'uncertainty': warnings, 'premises': ids}
        if conclusion not in response['conclusions']: response['conclusions'].append(conclusion)
    response['status'] = 'generated' if response['conclusions'] else 'abstained'
    response['reasons'] = sorted(failures) if not response['conclusions'] else []
    if not response['conclusions'] and not response['reasons']: response['reasons'] = ['required_premises_missing']
    return response

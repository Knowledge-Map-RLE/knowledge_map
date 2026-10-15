"""Применимость контекста определяется анализом и участниками, а не названием статьи."""
from copy import deepcopy
from math import isfinite
from domain.article_maps import digest, fingerprint, require

VERSION = 'analysis-scope-transfer-1'
SCOPE_KEYS = {'family', 'analysis_id', 'population_id', 'visit_id', 'level'}
FIELDS = {'dementia_excluded', 'minimum_age', 'matrix', 'followup_years', 'global_change', 'isolated_il6'}
UNIVERSAL_POPULATION_FIELDS = {'dementia_excluded', 'minimum_age'}

def validate_scope(scope):
    require(isinstance(scope, dict) and set(scope) == SCOPE_KEYS, 'Explicit analytical scope required')
    require(scope['level'] in {'cohort', 'analysis'}, 'Unknown scope level')
    require(all(v is None or isinstance(v, str) and bool(v.strip()) for k, v in scope.items() if k != 'level'), 'Invalid scope identity')

def validate_binding(binding, sources):
    require(set(binding) == {'article_id', 'source_sha256', 'evidence'}, 'Bound primary evidence required')
    require(binding['article_id'] in sources, 'Unknown primary source')
    source = sources[binding['article_id']]
    require(set(source) == {'text', 'sha256'} and digest(source['text']) == source['sha256'] == binding['source_sha256'], 'Primary source hash differs')
    require(isinstance(binding['evidence'], list) and bool(binding['evidence']), 'Primary evidence missing')
    for span in binding['evidence']:
        require(set(span) == {'start', 'end', 'text', 'offset_encoding'} and span['offset_encoding'] == 'unicode_code_points'
                and type(span['start']) is int and type(span['end']) is int
                and 0 <= span['start'] < span['end'] <= len(source['text'])
                and source['text'][span['start']:span['end']] == span['text'], 'Primary scope evidence differs')

def audit_scope_transfer(fact, target_scope, membership, sources):
    """Разрешение переноса контекста не является переносом эффекта или клиническим прогнозом."""
    require(set(fact) == {'id', 'field', 'value', 'scope', 'universal_population_fact', 'binding'}, 'Closed scope fact required')
    require(isinstance(fact['id'], str) and fact['id'] and fact['field'] in FIELDS, 'Unknown scope fact')
    require(type(fact['universal_population_fact']) is bool, 'Explicit universal assertion required')
    validate_scope(fact['scope']); validate_scope(target_scope); validate_binding(fact['binding'], sources)
    require(not fact['universal_population_fact'] or fact['scope']['level'] == 'cohort', 'Analysis-local fact cannot be universal')
    value = fact['value']
    if value is not None:
        if fact['field'] in {'minimum_age', 'followup_years'}:
            require(type(value) in {int, float} and isfinite(value) and value >= 0, 'Finite nonnegative quantity required')
        elif fact['field'] == 'matrix':
            require(value in {'plasma', 'serum', 'whole_blood', 'whole_blood_supernatant'}, 'Known specimen required')
        else:
            require(type(value) is bool, 'Explicit boolean context fact required')
    source_scope = fact['scope']
    if membership is not None:
        require(set(membership) == {'family', 'visit_id', 'parent_population_id', 'child_population_id', 'binding'}, 'Explicit subset proof required')
        require(all(isinstance(membership[k], str) and membership[k] for k in membership if k != 'binding'), 'Unknown subset identity')
        validate_binding(membership['binding'], sources)
    reasons = []
    if fact['value'] is None:
        reasons.append('unknown_fact_value')
    if any(source_scope[k] is None or target_scope[k] is None for k in ('family', 'visit_id', 'population_id')):
        reasons.append('unknown_population_or_origin')
    elif source_scope['family'] != target_scope['family']:
        reasons.append('different_family')
    elif source_scope['visit_id'] != target_scope['visit_id']:
        reasons.append('different_origin_visit')
    allowed = False
    if not reasons and source_scope['level'] == target_scope['level'] == 'analysis':
        if source_scope['analysis_id'] is None or target_scope['analysis_id'] is None:
            reasons.append('unknown_analysis_identity')
        elif source_scope['analysis_id'] != target_scope['analysis_id'] or source_scope['population_id'] != target_scope['population_id']:
            reasons.append('different_analysis_or_population')
        else:
            allowed = True
    elif not reasons and source_scope['level'] == 'cohort' and target_scope['level'] == 'analysis':
        if not fact['universal_population_fact'] or fact['field'] not in UNIVERSAL_POPULATION_FIELDS:
            reasons.append('not_universal_population_property')
        elif membership is None:
            reasons.append('subset_membership_not_proven')
        elif (membership['family'], membership['visit_id'], membership['parent_population_id'], membership['child_population_id']) != (
                source_scope['family'], source_scope['visit_id'], source_scope['population_id'], target_scope['population_id']):
            reasons.append('subset_membership_scope_differs')
        else:
            allowed = True
    elif not reasons:
        reasons.append('unsupported_scope_direction')
    result = {'version': VERSION, 'fact': deepcopy(fact), 'target_scope': deepcopy(target_scope),
              'membership': deepcopy(membership), 'context_inheritance_allowed': allowed, 'blockers': reasons,
              'resolved_context_value': deepcopy(fact['value']) if allowed else None,
              'empirical_effect_transfer_allowed': False, 'clinical_prediction': False,
              'expert_validated': False, 'model_calls': 0,
              'annotation_scope': 'Explicit identities and evidence are supplied by the annotator; this validator does not infer cohort/sample identity from article text.'}
    result['input_sha256'] = fingerprint({'fact': fact, 'target_scope': target_scope, 'membership': membership})
    return result

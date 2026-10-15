"""Консервативный эмпирический перенос по явным семантическим условиям."""
from copy import deepcopy
from dataclasses import asdict
from datetime import date
from domain.article_maps import fingerprint, require
from domain.empirical_question_forecast import CONTEXT, LABELS, ForecastRequest, Observation, eligibility, forecast
from domain.semantic_operator_learning import validate_frame

VERSION = 'guarded-empirical-transfer-1'
POLICY = {'version': VERSION, 'minimum_families': 2, 'required_equal_context': sorted(CONTEXT),
          'unknown_context': 'abstain', 'instrument_aliases': {'3mse': '3ms', '3ms': '3ms'},
          'bridge_policy': 'no unvalidated context bridges', 'scope': 'empirical_hypothesis_not_deduction',
          'numeric_effect_pooling': False, 'calibrated_probabilities': False}
POLICY_SHA256 = fingerprint(POLICY)


def canonical_context(context):
    value = deepcopy(context)
    if isinstance(value.get('instrument'), str):
        name = value['instrument'].strip().lower()
        value['instrument'] = POLICY['instrument_aliases'].get(name, name)
    return value


def compare_context(source, target):
    """Неизвестность не становится совпадением, даже при None с обеих сторон."""
    left, right = canonical_context(source), canonical_context(target)
    matched, unknown, different = [], [], []
    for key in sorted(CONTEXT):
        if left[key] is None or right[key] is None:
            unknown.append({'field': key, 'source': left[key], 'target': right[key]})
        elif left[key] != right[key]:
            different.append({'field': key, 'source': left[key], 'target': right[key]})
        else:
            matched.append(key)
    return {'applicable': not unknown and not different, 'matched': matched,
            'unknown': unknown, 'different': different, 'knowledge_equivalence': False}


def verify_record(record):
    require(isinstance(record, dict) and set(record) == {'observation', 'semantic_evidence'}, 'Exact transfer record required')
    observation = Observation(**record['observation'])
    observation.validate()
    evidence = record['semantic_evidence']
    require(set(evidence) == {'frame', 'frame_sha256', 'source_sha256', 'run_id', 'provenance', 'context_sha256',
                              'context_origin', 'projection_version', 'expert_validated', 'findings_sha256'}, 'Exact semantic evidence required')
    validate_frame(evidence['frame'])
    require(evidence['frame']['kind'] == 'state' and evidence['frame']['action_status'] is None, 'An intended action is not an empirical result')
    require(evidence['frame']['logic'] == 'single', 'Compound result requires an explicit projection; no automatic splitting')
    statement = evidence['frame']['statements'][0]
    require(not statement['negated'] and not statement['unknown_context'], 'Unresolved or negated frame cannot use these empirical labels')
    require(statement['predicate'] in {'associated with', 'estimated association', 'estimated hazard ratio'}, 'This operator accepts only empirical association results')
    attrs = {a['name']: a['value'] for a in statement['attributes']}
    require(attrs.get('evidence presentation') == 'own_result' and attrs.get('species') == 'human', 'Primary human result required')
    require(evidence['findings_sha256'] == fingerprint(observation.findings), 'Findings differ from bound semantic annotation')
    require(evidence['frame_sha256'] == fingerprint(evidence['frame']), 'Changed semantic frame')
    require(evidence['source_sha256'] == observation.binding['source_sha256'] and evidence['run_id'] == observation.binding['run_id'], 'Semantic evidence belongs to another source revision')
    require(evidence['context_sha256'] == fingerprint(observation.context), 'Context binding changed')
    require(isinstance(evidence['provenance'], list) and evidence['provenance'], 'Source provenance required')
    require(isinstance(evidence['context_origin'], dict) and evidence['context_origin'].get('sha256'), 'Audited context origin required')
    require(evidence['projection_version'] == 'schema6-operator-projection-2' and evidence['expert_validated'] is False,
            'This diagnostic requires the explicit unreviewed projection')
    require(observation.binding['claim_sha256'] == fingerprint(evidence), 'Observation differs from bound semantic evidence')
    return observation


def transfer(records, request):
    require(isinstance(request, ForecastRequest), 'Parsed context-only request required')
    observations = [verify_record(r) for r in records]
    require(len({o.reference for o in observations}) == len(observations), 'Repeated source observation')
    audits, admitted = [], []
    for observation in sorted(observations, key=lambda o: o.reference):
        reasons = list(eligibility(observation.context))
        if observation.family in request.excluded_families:
            reasons.append('heldout_family')
        if date.fromisoformat(observation.available_on) >= date.fromisoformat(request.as_of):
            reasons.append('not_strictly_earlier')
        comparison = compare_context(observation.context, request.context)
        if comparison['unknown']:
            reasons.append('unknown_transfer_context')
        if comparison['different']:
            reasons.append('unvalidated_context_difference')
        if not reasons:
            admitted.append(observation)
        audits.append({'reference': observation.reference, 'family': observation.family, 'reasons': sorted(set(reasons)),
                      'comparison': comparison, 'binding': observation.binding})
    # Голоса считаются по семьям, а не по числу публикаций или блоков.
    normalized_request = ForecastRequest.parse({**asdict(request), 'excluded_families': list(request.excluded_families),
                                                'context': canonical_context(request.context)})
    normalized = [Observation(**{**asdict(o), 'context': canonical_context(o.context)}) for o in admitted]
    result = forecast(normalized, normalized_request, 'frequency', minimum_families=POLICY['minimum_families'])
    result.update(version=VERSION, mode='guarded_transport', request={**asdict(request), 'excluded_families': list(request.excluded_families)},
                  policy=deepcopy(POLICY), policy_sha256=POLICY_SHA256, applicability=audits,
                  independent_admitted_families=sorted({o.family for o in admitted}),
                  scientific_success=False, operation_kind='empirical_transport_hypothesis',
                  author_dependency_rule_learned=False, causal_effect_established=False)
    for channel in LABELS:
        item = result['findings'].get(channel)
        if item and item['status'] == 'hypothesis':
            item['support_pattern'] = {'inputs': ['target_analysis_context', 'earlier_independent_source_results'],
                                       'conclusion': channel, 'joint_requirement': 'two applicable independent families',
                                       'origin': 'experimental_evidence_join_not_source_map_transition'}
    return result

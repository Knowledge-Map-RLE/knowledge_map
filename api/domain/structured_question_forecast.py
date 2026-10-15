"""Версионированный контекст и семейно-взвешенный вероятностный перенос по вопросу."""
from collections import defaultdict
from copy import deepcopy
from datetime import date
from math import exp, isfinite, log

from domain.article_maps import fingerprint, require

VERSION = 'structured-question-forecast-1'
CONTEXT_VERSION = 2
CHANNELS = {'reported_detection': ('detected', 'not_detected'),
            'point_direction': ('more_decline', 'less_decline', 'zero_point_estimate')}
FIELDS = {'schema_version', 'age_min', 'specimen', 'timing', 'exposure', 'outcome_scope',
          'instrument', 'estimand', 'contrast', 'mci', 'adjustment_class', 'time', 'baseline_dementia'}
TIME_FIELDS = {'study_horizon_years', 'study_horizon_basis', 'minimum_individual_years',
               'assessment_span_min_years', 'modeled_time_years', 'time_origin'}
VIEWS = {'reported_study_horizon', 'verified_individual_minimum'}
FEATURES = ('instrument', 'estimand', 'contrast', 'mci', 'adjustment_class', 'dementia_method', 'horizon_basis')
POLICY = {'version': VERSION, 'context_version': CONTEXT_VERSION, 'features': list(FEATURES),
          'smoothing': 1, 'minimum_families': 2, 'unknown_values': 'marginalize; never count as matching',
          'unseen_values': 'no learned evidence; report and omit likelihood factor',
          'family_budget': 'each independent family contributes at most one total observation weight per channel',
          'models': ['family_frequency', 'categorical_naive_bayes'], 'learned_from_training_only': True,
          'causal_or_logical_transport_license': False}

def validate_context(context):
    require(isinstance(context, dict) and set(context) == FIELDS and type(context['schema_version']) is int
            and context['schema_version'] == CONTEXT_VERSION, 'Explicit structured context version 2 required')
    for key in FIELDS - {'schema_version', 'time', 'baseline_dementia', 'age_min'}:
        require(context[key] is None or isinstance(context[key], str) and bool(context[key].strip()), 'Invalid categorical context')
    def quantity(value):
        require(value is None or type(value) in {int, float} and isfinite(value) and value >= 0, 'Finite nonnegative duration or age required')
    quantity(context['age_min'])
    time = context['time']
    require(isinstance(time, dict) and set(time) == TIME_FIELDS, 'Time meanings must be separate')
    for key in TIME_FIELDS - {'study_horizon_basis', 'time_origin'}: quantity(time[key])
    require(time['study_horizon_basis'] in {None, 'assessment_schedule_extent', 'scheduled_return', 'upper_horizon'}, 'Unknown study horizon meaning')
    require(time['time_origin'] in {None, 'baseline_exposure', 'cognitive_baseline'}, 'Unknown time origin')
    require(time['study_horizon_years'] is None or time['study_horizon_basis'] is not None, 'Known horizon needs an explicit meaning')
    dementia = context['baseline_dementia']
    require(isinstance(dementia, dict) and set(dementia) == {'operationally_excluded', 'method', 'adjudication_status'}, 'Dementia exclusion needs its method')
    require(dementia['operationally_excluded'] is None or type(dementia['operationally_excluded']) is bool, 'Explicit operational exclusion required')
    require(dementia['method'] in {None, 'screen_3ms_lt80', 'self_report_drug_history', 'authors_report_dementia_free', 'clinical_adjudication'}, 'Unknown exclusion method')
    require(dementia['adjudication_status'] in {'documented', 'not_documented', 'unknown'}, 'Explicit adjudication status required')
    require(dementia['operationally_excluded'] is not True or dementia['method'] is not None, 'Exclusion method missing')
    require(dementia['method'] != 'clinical_adjudication' or dementia['adjudication_status'] == 'documented', 'Adjudication cannot be inferred from screening')

def eligibility(context, view):
    validate_context(context)
    require(view in VIEWS, 'Explicit temporal eligibility view required')
    reasons = []
    checks = {'age_min': lambda v: v >= 60, 'specimen': lambda v: v == 'plasma',
              'timing': lambda v: v == 'single_baseline', 'exposure': lambda v: v == 'IL6',
              'outcome_scope': lambda v: v == 'global_change'}
    for key, check in checks.items():
        if context[key] is None: reasons.append('unknown:' + key)
        elif not check(context[key]): reasons.append('mismatch:' + key)
    if context['baseline_dementia']['operationally_excluded'] is None: reasons.append('unknown:baseline_exclusion')
    elif not context['baseline_dementia']['operationally_excluded']: reasons.append('mismatch:baseline_exclusion')
    key = 'study_horizon_years' if view == 'reported_study_horizon' else 'minimum_individual_years'
    if context['time'][key] is None: reasons.append('unknown:' + key)
    elif context['time'][key] < 2: reasons.append('mismatch:' + key)
    if context['time']['time_origin'] is None: reasons.append('unknown:time_origin')
    return reasons

def feature_values(context):
    validate_context(context)
    values = {key: context[key] for key in FEATURES[:5]}
    # Здесь только названия представления; клиническая истинность не выводится.
    values.update(dementia_method=context['baseline_dementia']['method'], horizon_basis=context['time']['study_horizon_basis'])
    return values

def validate_observation(row):
    require(set(row) == {'reference', 'family', 'available_on', 'context', 'findings', 'binding'}, 'Closed structured observation required')
    require(all(isinstance(row[k], str) and row[k] for k in ['reference', 'family']), 'Observation identity required')
    require(date.fromisoformat(row['available_on']).isoformat() == row['available_on'], 'Exact publication date required')
    validate_context(row['context'])
    require(set(row['findings']) == set(CHANNELS) and all(v is None or v in CHANNELS[k] for k, v in row['findings'].items()), 'Unknown finding channel')
    binding = row['binding']
    require(set(binding) == {'source_sha256', 'map_run_id', 'knowledge_id', 'frame_sha256', 'context_sha256', 'annotation_sha256'}, 'Bound context and semantic frame required')
    for key in ('source_sha256', 'frame_sha256', 'context_sha256', 'annotation_sha256'):
        value = binding[key]
        require(isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value), 'Invalid binding digest')
    require(all(isinstance(binding[k], str) and binding[k] for k in ('map_run_id', 'knowledge_id')), 'Map identities required')
    require(binding['context_sha256'] == fingerprint(row['context']), 'Bound context changed')

def validate_request(request):
    require(set(request) == {'reference', 'family', 'available_on', 'context'}, 'Request cannot contain target findings')
    require(all(isinstance(request[k], str) and request[k] for k in ('reference', 'family')), 'Request identities required')
    require(date.fromisoformat(request['available_on']).isoformat() == request['available_on'], 'Exact prediction date required')
    validate_context(request['context'])

def forecast(observations, request, model, view):
    validate_request(request)
    require(model in POLICY['models'] and view in VIEWS, 'No model or eligibility fallback')
    require(len({o['reference'] for o in observations}) == len(observations), 'Duplicate training reference')
    for row in observations: validate_observation(row)
    require(all(o['family'] != request['family'] for o in observations), 'Target family leaked into training')
    require(all(o['available_on'] < request['available_on'] for o in observations), 'Training must be strictly earlier')
    output = {'version': VERSION, 'policy_sha256': fingerprint(POLICY), 'request': deepcopy(request),
        'model': model, 'temporal_view': view, 'findings': {}, 'exclusions': [],
        'clinical_effect_prediction_confirmed': False, 'knowledge_equivalence': False,
        'causal_inference': False, 'probabilities_calibrated': False,
        'prediction_subject': 'reported point direction and author-defined detection, not biological truth',
        'training_sha256': fingerprint(observations), 'model_calls': 0}
    reasons = eligibility(request['context'], view)
    if reasons: return {**output, 'status': 'abstained', 'reasons': reasons}
    accepted = []
    for row in observations:
        reasons = eligibility(row['context'], view)
        if reasons: output['exclusions'].append({'reference': row['reference'], 'reasons': reasons})
        else: accepted.append(row)
    query_features = feature_values(request['context'])
    for channel, labels in CHANNELS.items():
        groups = defaultdict(list)
        for row in accepted:
            if row['findings'][channel] is not None: groups[row['family']].append(row)
        if len(groups) < POLICY['minimum_families']:
            output['findings'][channel] = {'status': 'abstained', 'families': len(groups), 'reason': 'insufficient_independent_families'}
            continue
        counts = {label: 0.0 for label in labels}
        tables = {key: {label: defaultdict(float) for label in labels} for key in FEATURES}
        evidence = []
        for family, rows in sorted(groups.items()):
            weight = 1 / len(rows)
            for row in rows:
                label = row['findings'][channel]; counts[label] += weight
                for key, value in feature_values(row['context']).items():
                    if value is not None: tables[key][label][value] += weight
            evidence.append({'family': family, 'total_weight': 1, 'references': [r['reference'] for r in rows]})
        prior = {label: (counts[label] + 1) / (len(groups) + len(labels)) for label in labels}
        log_scores = {label: log(prior[label]) for label in labels}
        feature_trace = []
        if model == 'categorical_naive_bayes':
            for key in FEATURES:
                vocab = sorted({value for label in labels for value in tables[key][label]})
                value = query_features[key]
                status = 'unknown_query' if value is None else 'unknown_training' if not vocab else 'unseen_query' if value not in vocab else 'used'
                row = {'field': key, 'query': value, 'status': status, 'vocabulary_from_training_only': vocab}
                if status == 'used':
                    conditional = {label: (tables[key][label][value] + 1) / (sum(tables[key][label].values()) + len(vocab)) for label in labels}
                    for label in labels: log_scores[label] += log(conditional[label])
                    row['conditional_likelihood'] = conditional
                feature_trace.append(row)
        maximum = max(log_scores.values())
        weights = {label: exp(score - maximum) for label, score in log_scores.items()}
        probabilities = {label: value / sum(weights.values()) for label, value in weights.items()}
        leaders = [label for label in labels if abs(probabilities[label] - max(probabilities.values())) < 1e-12]
        output['findings'][channel] = {'status': 'hypothesis', 'families': len(groups), 'prior': prior,
            'probabilities': probabilities, 'top_label': leaders[0] if len(leaders) == 1 else None,
            'feature_trace': feature_trace, 'family_evidence': evidence,
            'independence_assumption_validated': False, 'small_sample_diagnostic': True}
    output['status'] = 'hypothesis' if any(r['status'] == 'hypothesis' for r in output['findings'].values()) else 'abstained'
    return output

def evaluate(prediction, target):
    validate_observation(target)
    require({key: target[key] for key in ('reference', 'family', 'available_on', 'context')} == prediction['request'], 'Sealed target context differs')
    rows = []
    for channel, labels in CHANNELS.items():
        finding = prediction['findings'].get(channel, {'status': 'abstained'})
        truth = target['findings'][channel]
        row = {'channel': channel, 'truth': truth, 'status': finding['status']}
        if finding['status'] == 'hypothesis' and truth is not None:
            probs = finding['probabilities']
            require(set(probs) == set(labels) and all(type(v) in {int, float} and isfinite(v) and 0 <= v <= 1 for v in probs.values())
                    and abs(sum(probs.values()) - 1) < 1e-9, 'Invalid probability vector')
            row.update(brier=sum((probs[label] - (1 if label == truth else 0)) ** 2 for label in labels),
                       top_label=finding['top_label'], match=None if finding['top_label'] is None else finding['top_label'] == truth)
        rows.append(row)
    return rows

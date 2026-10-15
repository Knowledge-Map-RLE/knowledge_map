"""Временное сравнение не меняет часы опыта, эпизод лечения и квантор результата."""
from decimal import Decimal, InvalidOperation

from domain.article_maps import require

VERSION = 'typed-forecast-temporal-scope-2'
UNITS = {'minute': Decimal(1), 'hour': Decimal(60), 'day': Decimal(1440), 'week': Decimal(10080)}
QUANTIFIERS = {'some_assessed_time', 'all_assessed_times', 'specified_time', 'continuous_interval'}
BINDINGS = {'population', 'intervention', 'challenge', 'comparator', 'measurement', 'aggregate'}


def number(value):
    require(isinstance(value, str), 'Temporal numbers must be exact decimal strings')
    try: result = Decimal(value)
    except InvalidOperation: result = Decimal('NaN')
    require(result.is_finite(), 'Non-finite temporal bound')
    return result


def window(value, unit):
    require(set(value) == {'start', 'end', 'start_inclusive', 'end_inclusive'} and unit in UNITS,
            'Explicit temporal bounds and supported duration unit required')
    require(type(value['start_inclusive']) is type(value['end_inclusive']) is bool, 'Temporal boundaries are not booleans')
    start, end = number(value['start']) * UNITS[unit], number(value['end']) * UNITS[unit]
    require(start <= end and (start < end or value['start_inclusive'] and value['end_inclusive']), 'Empty temporal window')
    return start, end, value['start_inclusive'], value['end_inclusive']


def validate_contract(value):
    require(set(value) == {'anchor', 'unit', 'episode', 'time_quantifier', 'window', 'bindings'},
            'Temporal contract fields differ')
    require(value['anchor'] and value['episode'] and value['time_quantifier'] in QUANTIFIERS,
            'Temporal anchor, episode and quantifier required')
    require(set(value['bindings']) == BINDINGS and all(isinstance(v, str) and v for v in value['bindings'].values()),
            'Temporal context must bind participants, comparison and measurement')
    bounds = window(value['window'], value['unit'])
    require(value['time_quantifier'] != 'specified_time' or bounds[0] == bounds[1], 'Specified time must be one point')
    return bounds


def _overlap(a, b):
    start, end = max(a[0], b[0]), min(a[1], b[1])
    if start < end: return True
    if start > end: return False
    def contains(x, p):
        return x[0] <= p <= x[1] and (p != x[0] or x[2]) and (p != x[1] or x[3])
    return contains(a, start) and contains(b, start)


def _covers(a, b):
    return a[0] <= b[0] and a[1] >= b[1] and (a[0] != b[0] or a[2] or not b[2]) and (a[1] != b[1] or a[3] or not b[3])


def _contains(bounds, point):
    return bounds[0] <= point <= bounds[1] and (point != bounds[0] or bounds[2]) and (point != bounds[1] or bounds[3])


def compare_temporal(claim, observations, expected_direction):
    """Отдельная оценка времени; без контракта старое заключение не дополняется исходом."""
    if claim is None:
        return {'version': VERSION, 'status': 'missing_prediction_temporal_contract', 'supported': False,
                'contradicted': False, 'scientific_confirmation': False, 'matching_observation_ids': []}
    bounds = validate_contract(claim)
    require(expected_direction in {'lower', 'higher', 'equal'}, 'Unknown directional temporal claim')
    matches, opposites, excluded, uncertain = [], [], [], []
    for row in observations:
        require(set(row) == {'id', 'contract', 'direction', 'precision', 'evidence', 'assessment_times'}, 'Temporal observation fields differ')
        observed = row['contract']; other = validate_contract(observed)
        require(row['id'] and row['evidence'] and row['precision'] in {'exact', 'approximate'}
                and row['direction'] in {'lower', 'higher', 'equal', 'not_detected', 'unreported'}, 'Invalid observed temporal statement')
        require(isinstance(row['assessment_times'], list), 'Explicit known assessment points required')
        samples = [number(v) * UNITS[observed['unit']] for v in row['assessment_times']]
        require(samples == sorted(set(samples)) and all(_contains(other, t) for t in samples), 'Assessment points outside source window')
        require(row['precision'] != 'exact' or observed['time_quantifier'] != 'specified_time' or samples == [other[0]],
                'Exact observed point requires an explicit assessment')
        if any(claim[k] != observed[k] for k in ('anchor', 'episode', 'bindings')):
            excluded.append(row['id']); continue
        if row['precision'] != 'exact' or row['direction'] in {'not_detected', 'unreported'}:
            uncertain.append(row['id']); continue
        # Сплошной интервал не возникает из ежедневных измерений или одного конца окна.
        oq, cq = observed['time_quantifier'], claim['time_quantifier']
        # Универсальное утверждение о измеренных точках не устанавливает их существование.
        sample_overlap = any(_contains(bounds, t) for t in samples)
        if cq == 'some_assessed_time':
            enough = sample_overlap or oq == 'continuous_interval' and _overlap(bounds, other)
        elif cq == 'continuous_interval':
            enough = oq == 'continuous_interval' and _covers(other, bounds)
        elif cq == 'all_assessed_times':
            enough = oq in {'all_assessed_times', 'continuous_interval'} and _covers(other, bounds)
        else:
            enough = sample_overlap or oq == 'continuous_interval' and _covers(other, bounds)
        if row['direction'] == expected_direction:
            if enough: matches.append(row['id'])
            else: uncertain.append(row['id'])
        else:
            contrary = (_covers(other, bounds) and oq in {'all_assessed_times', 'continuous_interval'}
                        if cq == 'some_assessed_time' else sample_overlap or oq == 'continuous_interval' and _overlap(bounds, other))
            if contrary: opposites.append(row['id'])
            else: uncertain.append(row['id'])
        # Один противоположный знак опровергает универсальный квантор, но не существование в другом месте.
    status = 'conflicting_temporal_evidence' if matches and opposites else 'typed_temporal_direction_supported' if matches else 'typed_temporal_direction_contradicted' if opposites else 'temporal_evidence_insufficient'
    return {'version': VERSION, 'status': status, 'supported': bool(matches) and not opposites,
            'contradicted': bool(opposites) and not matches, 'scientific_confirmation': False,
            'matching_observation_ids': matches, 'opposite_observation_ids': opposites,
            'excluded_context_ids': excluded, 'uncertain_observation_ids': uncertain}


def infer_assessed_existence(receiver, observations, expected_direction):
    """Включение точки в окно и введение существования — вывод из источника, не прогноз."""
    method, measurement = [p['frame']['statements'][0] for p in receiver['body']]
    schedules = [a for a in method['attributes'] if a['name'] == 'EAE-relative days' and a['unit'] == 'day']
    endpoints = [a for a in measurement['attributes'] if a['name'] == 'explicit clinical observation end'
                 and a['unit'] == 'day after EAE onset']
    if len(schedules) != 1 or len(endpoints) != 1 or endpoints[0]['value'] is None:
        return {'status': 'explicit_method_window_unavailable', 'consequences': []}
    schedule = [number(v.strip()) for v in schedules[0]['value'].split(';')]
    require(schedule and schedule == sorted(set(schedule)), 'Explicit ordered dosing schedule required')
    end = number(endpoints[0]['value']); require(end >= schedule[-1], 'Observation ends before treatment course')
    consequences = []
    for row in observations:
        observed = row['contract']; validate_contract(observed)
        if observed['time_quantifier'] != 'specified_time' or row['precision'] != 'exact': continue
        role_values = {r['role']: r['value'] for r in method['roles']}
        require(all(observed['bindings'][k] == role_values[k] for k in ('population', 'intervention', 'challenge', 'comparator')),
                'Temporal source result belongs to another receiving procedure')
        require(observed['anchor'] == 'EAE disease onset' and observed['episode'] == 'initial_four_dose_course'
                and observed['bindings']['measurement'] == 'ordinal_eae_clinical_score'
                and observed['bindings']['aggregate'] == 'reported_group_comparison', 'Unlicensed source timeline')
        claim = {**observed, 'unit': 'day', 'time_quantifier': 'some_assessed_time',
            'window': {'start': str(schedule[0]), 'end': str(end), 'start_inclusive': True, 'end_inclusive': True}}
        proof = compare_temporal(claim, [row], expected_direction)
        if proof['supported']:
            consequences.append({'contract': claim, 'direction': expected_direction,
                'rule': 'point_in_method_window_then_existential_introduction', 'observation_id': row['id'],
                'proof': proof, 'method_premises': [receiver['body'][0]['key'], receiver['body'][1]['key']],
                'source_observation': row, 'is_future_prediction': False, 'is_new_scientific_fact': False})
    return {'status': 'source_temporal_inference', 'consequences': consequences}

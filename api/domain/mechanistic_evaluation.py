"""Оценка зафиксированной гипотезы по отдельному полному источнику, без обучения."""
from collections import Counter
from datetime import date
from hashlib import sha256

from domain.article_maps import fingerprint, require

VERSION = 'mechanistic-direction-evaluation-1'
FIELDS = ('species', 'disease', 'intervention', 'compartment')
STATUSES = ('direction_match', 'direction_contradiction', 'not_addressed',
            'incompatible_context', 'insufficient_information')


def evidence(source, rows):
    require(isinstance(rows, list) and bool(rows), 'Source evidence required')
    units = {u['id']: u for u in source['units']}
    require(len(units) == len(source['units']), 'Duplicate source unit')
    for row in rows:
        require(set(row) == {'unit_id', 'start', 'end', 'text', 'sha256'}, 'Exact evidence coordinates required')
        unit = units.get(row['unit_id'])
        require(unit is not None and type(row['start']) is int and type(row['end']) is int,
                'Unknown unit or invalid coordinates')
        require(0 <= unit['start'] <= row['start'] < row['end'] <= unit['end'] <= source['content_end'],
                'Evidence outside scientific text')
        text = source['text'][row['start']:row['end']]
        require(text == row['text'] and sha256(text.encode()).hexdigest() == row['sha256'],
                'Evidence or digest changed')


def validate_control(control, source, plan):
    require(control['author'] == 'Codex' and control['expert_validated'] is False
            and control['model_calls'] == 0, 'Explicit control authorship required')
    require(control['fulltext'] is True and control['primary_study'] is True, 'Primary full text required')
    require(control['source_sha256'] == source['sha256'] == sha256(source['text'].encode()).hexdigest(),
            'Control source digest changed')
    require(source['offset_encoding'] == 'Unicode code points' and type(source['content_end']) is int
            and 0 < source['content_end'] <= len(source['text']), 'Scientific source boundaries required')
    for unit in source['units']:
        require(type(unit['start']) is int and type(unit['end']) is int
                and 0 <= unit['start'] < unit['end'] <= len(source['text'])
                and source['text'][unit['start']:unit['end']] == unit['text'], 'Source unit changed')
    require(control['doi'] == source['doi'] and control['pmcid'] == source['pmcid'], 'Control identity changed')
    published = control['published_on']
    require(date.fromisoformat(published).isoformat() == published
            and published > plan['training_cutoff'], 'Control must be published after cutoff')
    require(control['source_version'] and control['limitations_ru'] and control['coverage_reason_ru'],
            'Control limits and coverage required')
    aliases = control['identity_licenses']
    require(len({x['alias'] for x in aliases}) == len(aliases), 'Duplicate identity license')
    for license in aliases:
        require(set(license) == {'alias', 'canonical', 'reason_ru', 'evidence'}, 'Exact identity license required')
        require(license['alias'] and license['canonical'] in plan['intervention_aliases']
                and license['reason_ru'], 'Unlicensed identity normalization')
        evidence(source, license['evidence'])
    require(len({r['id'] for r in control['observations']}) == len(control['observations']), 'Duplicate observation')
    for row in control['observations']:
        require(set(row) == {'id', 'context', 'route', 'outcome', 'measurement', 'polarity', 'direction',
                            'finding', 'p', 'negated', 'modality', 'action_status', 'direct_experiment',
                            'comparator', 'context_evidence', 'evidence', 'reason_ru', 'limits_ru'},
                'Exact observation contract required')
        require(set(row['context']) == set(FIELDS), 'Explicit observation context required')
        require(all(v is None or isinstance(v, str) and v for v in row['context'].values()), 'Invalid context')
        require(row['outcome'] in plan['outcome_policy'], 'Outcome outside sealed ontology')
        require(row['measurement'] and row['comparator'] and row['reason_ru'] and row['limits_ru'], 'Interpretation missing')
        require(row['direction'] in {'decrease', 'increase', 'no_clear_direction', 'unknown'}
                and row['polarity'] in {'identity', 'inverse'} and row['finding'] in {'detected', 'not_detected', 'not_reported'},
                'Unknown observation direction or statistical finding')
        require(type(row['negated']) is bool and type(row['direct_experiment']) is bool
                and row['modality'] in {'observed', 'hypothesized', 'cited'}
                and row['action_status'] in {'performed', 'intended', 'unresolved'}, 'Explicit observation status required')
        evidence(source, row['context_evidence']); evidence(source, row['evidence'])
    for absent in control['unmeasured']:
        require(set(absent) == {'outcome', 'reason_ru', 'evidence'}
                and absent['outcome'] in plan['outcome_policy'] and absent['reason_ru'], 'Unmeasured outcome audit required')
        require(not any(r['outcome'] == absent['outcome'] and r['direct_experiment'] for r in control['observations']),
                'Measured outcome also declared absent')
        evidence(source, absent['evidence'])


def compare(candidate, observation, control, plan):
    expected = candidate['conclusion']; actual = dict(observation['context']); blockers = []
    aliases = {r['alias']: r['canonical'] for r in control['identity_licenses']}
    actual['intervention'] = aliases.get(actual['intervention'], actual['intervention'])
    if any(actual[k] is None for k in FIELDS):
        return {'observation_id': observation['id'], 'status': 'insufficient_information', 'blockers': ['unknown_context']}
    for key in FIELDS:
        if expected[key] != actual[key]: blockers.append('different_' + key)
    if observation['route'] is None: blockers.append('unknown_route')
    elif observation['route'] not in expected['routes']: blockers.append('different_route')
    if blockers:
        status = 'insufficient_information' if 'unknown_route' in blockers and len(blockers) == 1 else 'incompatible_context'
        return {'observation_id': observation['id'], 'status': status, 'blockers': blockers}
    if (not observation['direct_experiment'] or observation['negated'] or observation['modality'] != 'observed'
            or observation['action_status'] != 'performed' or observation['direction'] in {'unknown', 'no_clear_direction'}):
        return {'observation_id': observation['id'], 'status': 'insufficient_information', 'blockers': ['not_a_direct_directional_result']}
    direction = observation['direction']
    if observation['polarity'] == 'inverse': direction = {'decrease': 'increase', 'increase': 'decrease'}[direction]
    return {'observation_id': observation['id'], 'status': 'direction_match' if direction == expected['expected_direction'] else 'direction_contradiction',
            'blockers': [], 'normalized_direction': direction, 'statistical_finding': observation['finding'], 'p': observation['p'],
            'measurement': observation['measurement'], 'polarity': observation['polarity'], 'limits_ru': observation['limits_ru'],
            'evidence': observation['evidence'], 'context_evidence': observation['context_evidence']}


def evaluate(forecast, plan, control, source):
    require(plan['version'] == 'mechanistic-opportunity-evaluation-1' and plan['model_calls'] == 0
            and plan['forecast_run_id'] == forecast['run_id'] and plan['forecast_sha256'] == fingerprint(forecast),
            'Frozen forecast or plan changed')
    require(tuple(plan['contexts_required_equal']) == FIELDS and set(plan['statuses']) == set(STATUSES), 'Evaluation policy differs')
    candidates = forecast['candidates']['without_dependencies']
    require(sorted(plan['hypothesis_ids']) == sorted(c['id'] for c in candidates), 'Frozen hypothesis set changed')
    validate_control(control, source, plan)
    rows = {}
    for candidate in candidates:
        outcome = candidate['conclusion']['outcome']
        matches = [compare(candidate, row, control, plan) for row in control['observations'] if row['outcome'] == outcome]
        statuses = {m['status'] for m in matches}
        conflict = {'direction_match', 'direction_contradiction'} <= statuses
        if conflict: status = 'insufficient_information'
        elif 'direction_contradiction' in statuses: status = 'direction_contradiction'
        elif 'direction_match' in statuses: status = 'direction_match'
        elif 'insufficient_information' in statuses: status = 'insufficient_information'
        elif matches: status = 'incompatible_context'
        else:
            require(any(u['outcome'] == outcome for u in control['unmeasured']), 'Missing explicit absence audit')
            status = 'not_addressed'
        rows[candidate['id']] = {'candidate_id': candidate['id'], 'outcome': outcome, 'outcome_ru': candidate['outcome_ru'],
            'status': status, 'mixed_directions': conflict, 'comparisons': matches,
            'absence': [u for u in control['unmeasured'] if u['outcome'] == outcome],
            'scientific_fact_equivalence': False, 'causality_confirmed': False}
    modes = {}
    for mode, members in forecast['candidates'].items():
        require(len({c['id'] for c in members}) == len(members) and all(c['id'] in rows for c in members), 'Unknown mode candidate')
        for c in members:
            require(c['conclusion'] == next(v['conclusion'] for v in candidates if v['id'] == c['id']), 'Mode conclusion changed')
        mode_rows = [rows[c['id']] for c in members]
        modes[mode] = {'candidates': len(members), 'counts': dict(Counter(r['status'] for r in mode_rows)), 'rows': mode_rows}
    return {'version': VERSION, 'forecast_run_id': forecast['run_id'], 'control_sha256': fingerprint(control),
            'source_sha256': source['sha256'], 'plan_sha256': fingerprint(plan), 'modes': modes,
            'baseline_evaluation': 'not_evaluated_as_new_hypotheses; incompatible raw-block output contract',
            'model_calls': 0, 'forecast_changed': False, 'scientific_success': False,
            'graph_advantage_demonstrated': False, 'expert_validated': False,
            'historical_blindness_certified': False, 'chronological_first_control_resolved': False}

"""Интервальная арифметика не становится тестом эффекта или вероятностью параметра."""
from copy import deepcopy
from decimal import Decimal, InvalidOperation, localcontext
from hashlib import sha256
import re

from domain.article_maps import fingerprint, require
from domain.comparison_normalization import normalize_map
from domain.evidence_origin_audit import validate_origins
from domain.protocol_parameter_transfer import protocol_frame_identity
from domain.semantic_part_forecast import align_groups, primary_support, apply_templates
from domain.typed_participant_forecast import learn
from domain.whole_map_ablation import source_neighborhood_groups, permuted_groups

VERSION = 'source-bound-interval-knowledge-2'
FOUNDATION = {'interval_difference': '[a,b] - [c,d] = [a-d,b-c]',
    'joint_coverage_bound': 'P(A intersection B) >= max(0,P(A)+P(B)-1)',
    'reference': 'https://www.itl.nist.gov/div898/handbook/prc/section4/prc463.htm'}


def decimal(value):
    require(isinstance(value, str), 'Interval values require exact decimal strings')
    require(bool(re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?', value, re.ASCII)), 'Invalid decimal syntax')
    try: result = Decimal(value)
    except InvalidOperation: result = Decimal('NaN')
    require(result.is_finite(), 'Non-finite interval value')
    require(len(result.as_tuple().digits) <= 2048 and abs(result.as_tuple().exponent) <= 4096, 'Interval precision exceeds explicit limits')
    return result


def _precision(values):
    return max(1, max(max(0, v.adjusted()+1) for v in values) + max(max(0, -v.as_tuple().exponent) for v in values) + 4)


def geometry(left, right):
    """Концы относятся к напечатанным границам; их округление не восстанавливается."""
    require(isinstance(left, list) and isinstance(right, list) and len(left) == len(right) == 2, 'Interval needs two explicit bounds')
    a, b = decimal(left[0]), decimal(left[1]); c, d = decimal(right[0]), decimal(right[1])
    require(a <= b and c <= d, 'Reversed interval bounds')
    with localcontext() as context:
        context.prec = _precision([a,b,c,d]); lo, hi = a-d, b-c
    overlap = max(a, c) <= min(b, d)
    return {'difference': [format(lo,'f'), format(hi,'f')], 'overlap': overlap,
        'overlap_bounds': [format(max(a,c),'f'), format(min(b,d),'f')] if overlap else None,
        'zero_in_difference': lo <= 0 <= hi, 'difference_direction': 'positive' if lo > 0 else 'negative' if hi < 0 else 'not_forced',
        'statistical_detection_inferred': False, 'effect_absence_inferred': False}


def coverage_bound(left_percent, right_percent):
    """Независимость не предполагается; гарантия только при действительных процедурах ДИ."""
    a, b = decimal(left_percent), decimal(right_percent)
    require(0 < a <= 100 and 0 < b <= 100, 'Invalid confidence coefficient')
    with localcontext() as context:
        context.prec = _precision([a,b,Decimal(100)]); value = max(Decimal(0), a+b-100)
    return {'conditional_joint_coverage_percent_at_least': format(value,'f'),
        'assumed_independence': False, 'parameter_probability_asserted': False,
        'actual_coverage_verified': False, 'reported_rounded_bounds_coverage_verified': False,
        'assumptions_ru': ['Обе процедуры действительно имеют указанные нижние границы частотного покрытия.',
            'Для гарантии разности нужны соответствующие действительные границы, а не только их округлённая печатная запись.',
            'Выбор параметров и процедуры не нарушает заявленного покрытия.']}


def _quote(evidence, source, allowed):
    units = {u['id']: u for u in source['units']}
    require(evidence['unit_id'] in allowed and evidence['unit_id'] in units, 'Interval quote outside statement provenance')
    u = units[evidence['unit_id']]; start, end = evidence['start'], evidence['end']
    require(u['start'] <= start < end <= u['end'] <= source['content_end']
            and source['text'][start:end] == evidence['text']
            and sha256(evidence['text'].encode()).hexdigest() == evidence['sha256'], 'Interval quote changed')


def compile_entries(frozen, maps, origin_audit, audit):
    """Источник связывает оценки групп и область; геометрия не подменяет сравнение автора."""
    require(audit['version'] == VERSION and audit['author'] == 'Codex' and audit['model_calls'] == 0
            and audit['expert_validated'] is False and audit['input_sha256'] == fingerprint(frozen), 'Interval audit binding differs')
    origins = validate_origins(maps, origin_audit); require(origins is not None, 'Complete interval origin registry required')
    catalog = {m['article_id']: m for m in maps}; native = {(m['article_id'], k['knowledge_id']): k for m in maps for k in m['graph']['knowledge']}
    views = {tuple(v['key']): deepcopy(v) for v in frozen['part_views']}; require(len(views) == len(frozen['part_views']), 'Repeated interval view')
    result, entries, used = [], {}, set()
    for e in audit['entries']:
        key = tuple(e['native_key']); require(key in native, 'Unknown interval knowledge')
        identity = (key, e['statement_id']); require(identity not in used, 'Repeated interval statement license'); used.add(identity)
        m, k = catalog[key[0]], native[key]
        require(e['run_id'] == m['run_id'] and e['source_sha256'] == m['source']['sha256']
                and e['knowledge_sha256'] == fingerprint(k), 'Interval parent binding differs')
        statement = next((s for s in k['semantic_frame']['statements'] if s['statement_id'] == e['statement_id']), None)
        require(statement is not None and k['kind'] == 'state' and k['action_status'] is None, 'Interval belongs to an action or missing state')
        origin = next(a for a in origins['knowledge'][key]['statements'] if a['statement_id'] == e['statement_id'])
        require(origins['sources'][key[0]]['document_kind'] == 'primary_study' and origin['origin'] == 'primary_result', 'Interval is not an own primary observation')
        allowed = set(statement['provenance']['unit_ids'])
        require(e['estimand_ru'] and e['clock_ru'] and e['reason_ru'] and len(e['intervals']) == 2, 'Incomplete interval interpretation')
        for q in e['evidence']: _quote(q, m['source'], allowed)
        require(e['evidence'], 'Interval license lacks source quote')
        choices = [v for v in views.values() if tuple(v['native_key']) == key
                   and v['projection_proof']['origin']['statement_id'] == e['statement_id']]
        require(choices, 'Interval statement has no licensed semantic part')
        frame = choices[0]['frame']; s = frame['statements'][0]
        require(frame['logic'] == 'single' and not s['negated'] and s['scope']['modality'] is None,
                'Negated or modal interval requires another operator')
        attrs = {a['name']: a for a in s['attributes']}; require(len(attrs) == len(s['attributes']), 'Ambiguous interval fields')
        result_text = ' '.join(q['text'] for q in e['evidence'])
        require(e['reported_detection'] in {'detected', 'not_detected'}, 'Unknown source test status')
        require((e['reported_detection'] == 'detected' and s['predicate'] == 'onset delayed after intervention'
                 and 'significant delay' in result_text)
                or (e['reported_detection'] == 'not_detected' and s['predicate'] == 'onset delay not statistically established'
                    and 'delay was not significant' in result_text), 'Test status not licensed by the source claim')
        level = attrs[e['level_field']]; require(level['unit'] == 'percent', 'Explicit interval confidence unit required')
        require(e['level_field'] == 'ci level' and level['value'] + '% CI' in result_text, 'Confidence coefficient absent from source statement')
        parsed, fields = [], {e['level_field']}
        for interval in e['intervals']:
            require(interval['lower_field'].endswith(' ci lower') and interval['upper_field'] == interval['lower_field'][:-5] + 'upper',
                    'Fields are not a declared pair of confidence bounds')
            lo, hi = attrs[interval['lower_field']], attrs[interval['upper_field']]
            require(lo['unit'] == hi['unit'] == e['unit'] and e['unit'], 'Interval estimands have different or unknown units')
            require(interval['label_ru'], 'Interval participant not declared')
            require(str(lo['value']) in ' '.join(q['text'] for q in e['evidence'])
                    and str(hi['value']) in ' '.join(q['text'] for q in e['evidence']), 'Interval values absent from exact source quote')
            fields.update((interval['lower_field'], interval['upper_field']))
            parsed.append({'label_ru': interval['label_ru'], 'bounds': [lo['value'], hi['value']], 'unit': e['unit']})
        proof = {'native_key': list(key), 'run_id': m['run_id'], 'statement_id': e['statement_id'],
            'complete_native_knowledge': deepcopy(k), 'source_sha256': m['source']['sha256'], 'evidence': deepcopy(e['evidence']),
            'estimand_ru': e['estimand_ru'], 'clock_ru': e['clock_ru'], 'scope': deepcopy(s['scope']),
            'intervals': parsed, 'geometry': geometry(parsed[0]['bounds'], parsed[1]['bounds']),
            'coverage': coverage_bound(level['value'], level['value']), 'reported_detection': e['reported_detection'],
            'reported_detection_inferred_by_operator': False, 'input_bounds_precision': 'printed_rounded',
            'new_empirical_measurement': False, 'future_prediction': False, 'scientific_confirmation': False,
            'expert_validated': False, 'foundation': FOUNDATION}
        proof['id'] = fingerprint(proof); result.append(proof)
        # Положительное качественное утверждение уже находится в источнике; числа остаются в доказательстве.
        if s['predicate'] == 'onset delayed after intervention':
            for v in choices:
                vs = v['frame']['statements'][0]
                require({a['name']: a for a in vs['attributes']} == attrs, 'Interval variants have different numbers or conditions')
                original = deepcopy(v['frame'])
                vs['attributes'] = [a for a in vs['attributes'] if a['name'] not in fields]
                p = v['projection_proof']; p['interval_summary_proof'] = {'operator': VERSION, 'interval_proof_id': proof['id'],
                    'complete_input_frame': original, 'removed_summary_fields': sorted(fields),
                    'scope_changed': False, 'participants_changed': False, 'future_confidence_predicted': False}
                p['view_frame_sha256'] = fingerprint(v['frame']); p.pop('id', None); p['id'] = fingerprint(p)
                entries[tuple(v['key'])] = v
    require(audit['map_hashes'] == [fingerprint(m) for m in maps], 'Interval corpus hashes differ')
    return result, entries, origins


def _learn_modes(views, maps, origins, families, known):
    views = {k: {**v, 'key': k, 'native_key': tuple(v['native_key'])} for k, v in views.items()}
    records, groups = {}, []
    by_parent = {(m['article_id'], k['knowledge_id']): [] for m in maps for k in m['graph']['knowledge']}
    for key, v in views.items(): by_parent[v['native_key']].append(key)
    for m in maps:
        for k in normalize_map(m):
            key = (m['article_id'], k['id']); records[key] = {'provenance': [s['provenance'] for s in k['statements']]}
            groups.extend((tuple((key[0], p) for p in g), key) for g in k['premise_groups'])
    outputs = {}
    for mode, selected in (('graph', groups), ('source_neighborhood_without_dependencies', source_neighborhood_groups(records)),
                           ('permuted_dependencies', permuted_groups(records, groups))):
        aligned, alignment = align_groups(views, by_parent, selected)
        rules, diagnostics = learn(views, aligned, families); accepted, support = primary_support(rules, views, origins)
        candidates, application = apply_templates(views, by_parent, accepted, selected, known, mode != 'source_neighborhood_without_dependencies')
        outputs[mode] = {'rules': accepted, 'learning': diagnostics, 'support': support, 'alignment': alignment,
                         'predictions': candidates, 'application': application}
        if mode == 'graph':
            flat, application = apply_templates(views, by_parent, accepted, selected, known, False)
            outputs['same_rules_without_dependencies'] = {'predictions': flat, 'application': application, 'same_rules': True}
    return outputs


def analyze(baseline, frozen, maps, origin_audit, audit):
    require(baseline['version'] == 'whole-map-typed-participant-forecast-3' and baseline['run_id'] == fingerprint(baseline['binding'])
            and baseline['binding']['source_sha256'] == fingerprint(frozen)
            and frozen['binding']['map_hashes'] == [fingerprint(m) for m in maps], 'Interval source forecast differs')
    proofs, changed, origins = compile_entries(frozen, maps, origin_audit, audit)
    views = {tuple(v['key']): deepcopy(v) for v in frozen['part_views']}; projected = {**views, **changed}
    known = {protocol_frame_identity(v['frame']) for v in (*views.values(), *projected.values())}
    for m in maps:
        for k in normalize_map(m):
            for s in k['statements']:
                atom = {n: deepcopy(s[n]) for n in ('predicate', 'roles', 'scope', 'attributes', 'negated')}
                known.add(protocol_frame_identity({'kind': k['kind'], 'action_status': k['action_status'], 'logic': 'single', 'statements': [atom]}))
    policies = {}
    for policy, selected in (('before_interval_summary', views), ('source_bound_interval_summary', projected)):
        policies[policy] = _learn_modes(selected, maps, origins, frozen['binding']['families'], known)
    for mode in ('graph', 'source_neighborhood_without_dependencies', 'permuted_dependencies'):
        require(fingerprint(policies['before_interval_summary'][mode]['learning']) == fingerprint(
            baseline['policies']['typed_concept_participants'][mode]['learning']), 'Interval baseline learning changed')
    coverage = []
    for m in maps:
        for k in normalize_map(m):
            interval_fields = [{'statement_id': s['id'], 'attributes': [deepcopy(a) for a in s['attributes']
                if 'ci' in a['name'].split() or 'ci95' in a['name'] or 'confidence' in a['name']]} for s in k['statements']]
            coverage.append({'native_key': [m['article_id'], k['id']], 'statements': len(k['statements']),
                'interval_fields': interval_fields, 'has_licensed_pair': any(p['native_key'] == [m['article_id'], k['id']] for p in proofs)})
    return {'version': VERSION, 'canonical_blocks': len(coverage), 'semantic_statements': sum(c['statements'] for c in coverage),
        'licensed_parts': len(views), 'coverage': coverage, 'interval_consequences': proofs,
        'projected_views': list(changed.values()), 'policies': policies, 'baseline_learning_reproduced': True,
        'model_calls': 0, 'target_read': False, 'question': None, 'independent_future_validation': False,
        'scientific_success': False, 'graph_advantage_demonstrated': False}

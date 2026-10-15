"""Область применения общего оператора не подменяет точный контекст опытов."""
from collections import Counter, defaultdict
from copy import deepcopy
from hashlib import sha256

from domain.article_maps import fingerprint, require
from domain.comparison_normalization import normalize_map
from domain.evidence_origin_audit import validate_origins

VERSION = 'source-bound-operation-applicability-1'
AXES = ('species', 'disease_model', 'target', 'intervention_action', 'route', 'phase', 'measurement_kind')
PHASES = {'prophylactic', 'manifest_disease'}
CHALLENGE = {'mog35-55-induced eae', 'mog35-55-induced experimental autoimmune encephalomyelitis'}


def compare_features(left, right):
    """Даже две одинаковые неизвестности не дают разрешение на перенос."""
    require(set(left) == set(right) == set(AXES), 'Exact applicability axes required')
    different, unknown, equal = [], [], []
    for axis in AXES:
        a, b = left[axis], right[axis]
        if a is None or b is None: unknown.append(axis)
        elif a != b: different.append(axis)
        else: equal.append(axis)
    return {'applicable': not different and not unknown, 'matched': equal, 'different': different,
            'unknown': unknown, 'experimental_equivalence': False, 'deductive_entailment': False}


def analyze(forecast, maps, origin_audit, audit):
    require(forecast['run_id'] == fingerprint(forecast['binding']) and forecast['question'] is None
            and forecast['model_calls'] == 0 and forecast['target_read'] is False, 'Invalid input forecast')
    require(audit['version'] == VERSION and audit['author'] == 'Codex' and audit['model_calls'] == 0
            and audit['expert_validated'] is False and audit['input_run_id'] == forecast['run_id']
            and audit['input_sha256'] == fingerprint(forecast), 'Applicability provenance differs')
    origins = validate_origins(maps, origin_audit)
    require(origins is not None, 'Explicit complete origin audit required')
    catalog = {m['article_id']: m for m in maps}
    require(set(catalog) == {r['article_id'] for r in forecast['binding']['references']}, 'Applicability corpus differs')
    native = {(m['article_id'], k['knowledge_id']): k for m in maps for k in m['graph']['knowledge']}
    views = {tuple(v['key']): v for v in forecast['part_views']}
    require(len(views) == len(forecast['part_views']), 'Repeated applicability view')
    groups = set()
    for m in maps:
        require(sha256(m['source']['text'].encode()).hexdigest() == m['source']['sha256']
                and m['source']['offset_encoding'] == 'unicode_codepoints', 'Applicability source differs')
        for k in normalize_map(m):
            groups.update((frozenset((m['article_id'], p) for p in g), (m['article_id'], k['id'])) for g in k['premise_groups'])
    entries, seen, coverage = [], set(), Counter()
    for c in audit['cases']:
        require(c['id'] not in seen and bool(c['reason_ru']), 'Repeated or unexplained case'); seen.add(c['id'])
        selected = [views[tuple(c[field])] for field in ('method', 'measurement', 'result')]
        method, measurement, result = selected
        article = method['native_key'][0]; m = catalog[article]
        require(all(v['native_key'][0] == article and v['run_id'] == m['run_id'] for v in selected), 'Case crosses studies')
        require(c['source_sha256'] == m['source']['sha256'] and c['graph_sha256'] == fingerprint(m['graph']), 'Case source binding differs')
        for v, expected_origin in zip(selected, ['primary_method', 'primary_method', 'primary_result']):
            proof = v['projection_proof']
            require(proof['view_frame_sha256'] == fingerprint(v['frame'])
                    and proof['complete_native_knowledge'] == native[tuple(v['native_key'])]
                    and proof['origin']['origin'] == expected_origin
                    and proof['origin'] in origins['knowledge'][tuple(v['native_key'])]['statements'],
                    'Case part or origin differs')
            require(v['frame']['logic'] == 'single' and len(v['frame']['statements']) == 1, 'Licensed single case part required')
            s = v['frame']['statements'][0]
            require(len({r['role'] for r in s['roles']}) == len(s['roles']), 'Repeated case participant role')
            require(not s['negated'] and s['scope']['modality'] is None and s['scope']['quantifier'] is None,
                    'Negated, modal or quantified evidence needs another operator')
        require(all(v['frame']['kind'] == 'action' and v['frame']['action_status'] == 'performed' for v in selected[:2])
                and result['frame']['kind'] == 'state' and result['frame']['action_status'] is None,
                'Case action or result status differs')
        require(method['frame']['statements'][0]['predicate'] == 'administer treatment'
                and measurement['frame']['statements'][0]['predicate'] == 'measure clinical course', 'Unsupported operation pair')
        body = frozenset(tuple(v['native_key']) for v in selected[:2]); head = tuple(result['native_key'])
        require(len(body) == 2 and (body, head) in groups, 'Case lacks its author joint group')
        source_info = origins['sources'][article]
        require(source_info['document_kind'] == 'primary_study' and source_info['dataset_family'], 'Own primary dataset required')
        basis = {tuple(k) for k in c['basis']}
        require(body | {head} <= basis and all(k in native and k[0] == article for k in basis), 'Case basis crosses source or omits parents')
        units = {u['id']: u for u in m['source']['units']}
        allowed = {u for k in basis for s in native[k]['semantic_frame']['statements'] for u in s['provenance']['unit_ids']}
        require(set(c['features']) == set(AXES) == set(c['feature_evidence']), 'Applicability feature registry differs')
        require(c['features']['phase'] in PHASES or c['features']['phase'] is None, 'Unknown phase classification')
        require(all(value is None or isinstance(value, str) and value.strip() for value in c['features'].values()), 'Invalid feature value')
        for axis in (*AXES, 'qualitative_direction'):
            evidence = c['direction_evidence'] if axis == 'qualitative_direction' else c['feature_evidence'][axis]
            require(isinstance(evidence, list) and (bool(evidence) or axis != 'qualitative_direction' and c['features'][axis] is None), 'Known feature lacks source evidence')
            for e in evidence:
                require(e['source_asserts_feature'] is True and e['unit_id'] in allowed, 'Unlicensed feature evidence')
                if axis == 'qualitative_direction':
                    require(e['unit_id'] in result['projection_proof']['selected_provenance']['unit_ids'],
                            'Direction must come from this own result part')
                u = units[e['unit_id']]
                require(u['start'] <= e['start'] < e['end'] <= u['end'] <= m['source']['content_end']
                        and m['source']['text'][e['start']:e['end']] == e['text']
                        and sha256(e['text'].encode()).hexdigest() == e['sha256'], 'Feature source fragment differs')
        ms, hs = method['frame']['statements'][0], result['frame']['statements'][0]
        mr = {r['role']: r['value'] for r in ms['roles']}; hr = {r['role']: r['value'] for r in hs['roles']}
        require(all(role in mr and role in hr and mr[role] == hr[role] for role in ('intervention', 'population')),
                'Result belongs to another intervention or population')
        require(mr.get('challenge') in CHALLENGE and hr.get('challenge') in CHALLENGE, 'Disease model is not linked')
        measured = measurement['frame']['statements'][0]
        measured_roles = {r['role']: r['value'] for r in measured['roles']}
        require(measured_roles.get('population') == mr['population']
                and measured_roles.get('challenge') in CHALLENGE,
                'Measurement belongs to another population or challenge')
        require(any(r['role'] == 'outcome' and r['value'] == 'eae clinical score' for r in measured['roles']),
                'Clinical outcome has no linked measurement')
        require(c['outcome_class'] == 'clinical_eae_burden' and hr.get('outcome') in {
            'eae clinical progression', 'eae motor symptoms and cumulative clinical score'}, 'This outcome class is not licensed')
        require(hs['predicate'] in {'reduced after intervention', 'improved after intervention'}
                and c['qualitative_direction'] == 'lower_clinical_burden', 'This case has no licensed outcome orientation')
        comparison = compare_features(c['features'], c['features'])
        row = {'case_id': c['id'], 'article_id': article, 'run_id': m['run_id'], 'primary_family': source_info['dataset_family'],
            'features': deepcopy(c['features']), 'applicability_complete': comparison['applicable'],
            'unknown_axes': comparison['unknown'], 'outcome_class': c['outcome_class'], 'predicate': hs['predicate'],
            'qualitative_direction': c['qualitative_direction'],
            'method': deepcopy(method), 'measurement': deepcopy(measurement), 'result': deepcopy(result),
            'source_annotation': deepcopy(c), 'complete_basis': [{'native_key': list(k), 'knowledge': deepcopy(native[k])} for k in sorted(basis)],
            'scope_and_numbers_retained': True, 'claims_experimental_equivalence': False,
            'source_interpretation_requires_expert_review': True}
        entries.append(row); coverage['complete_contract' if comparison['applicable'] else 'unknown_contract_axes'] += 1
    buckets = defaultdict(list)
    for e in entries:
        if not e['applicability_complete']: continue
        shape = {'features': e['features'], 'body': ['administer treatment', 'measure clinical course'],
                 'head': e['qualitative_direction'], 'outcome_class': e['outcome_class'], 'negated': False,
                 'logic': 'single', 'head_kind': 'state', 'action_status': 'performed_premises',
                 'joint_parent_group_required_in_evidence': True}
        buckets[fingerprint(shape)].append((shape, e))
    schemata = []
    for key, rows in sorted(buckets.items()):
        families = sorted({e['primary_family'] for _, e in rows})
        schema = {'id': key, 'shape': deepcopy(rows[0][0]), 'primary_families': families,
                  'case_ids': sorted(e['case_id'] for _, e in rows), 'minimum_primary_support': len(families) >= 2,
                  'status': 'candidate_operator_schema', 'valid_universal_rule': False, 'new_prediction': False,
                  'conditional_transfer_requires_full_context_check': True, 'graph_advantage_demonstrated': False}
        schemata.append(schema)
    comparisons = [{'left': a['case_id'], 'right': b['case_id'], **compare_features(a['features'], b['features'])}
                   for i, a in enumerate(entries) for b in entries[i + 1:]]
    selected_keys = {tuple(v['key']) for e in entries for v in (e['method'], e['measurement'], e['result'])}
    return {'version': VERSION, 'input_run_id': forecast['run_id'], 'canonical_blocks': forecast['canonical_blocks'],
            'licensed_parts': len(views), 'cases': entries, 'schemata': schemata, 'comparisons': comparisons,
            'coverage': {'all_input_views_enumerated': True, 'contract_views': len(selected_keys),
                         'without_explicit_contract': len(views) - len(selected_keys), **dict(coverage)},
            'new_predictions': 0, 'scientific_success': False, 'graph_advantage_demonstrated': False,
            'model_calls': 0, 'target_read': False,
            'policy_ru': 'Общая форма оператора хранится отдельно от полного контекста каждого опыта. '
                         'Источниковые классы не делают эксперименты эквивалентными. Неизвестность и другая фаза '
                         'блокируют объединение. Поддержанная схема не является прогнозом или универсальным законом.'}

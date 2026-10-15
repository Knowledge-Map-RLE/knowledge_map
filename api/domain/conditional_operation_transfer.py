"""Перенос источниковой схемы отделён от результатов принимающего исследования."""
from collections import Counter, defaultdict
from copy import deepcopy

from domain.article_maps import fingerprint, require
from domain.operation_applicability import AXES, compare_features

VERSION = 'family-held-out-operation-transfer-3'
MODES = ('graph', 'without_dependencies', 'permuted_dependencies')
RECEIVER_FIELDS = {'id', 'article_id', 'run_id', 'primary_family', 'features',
                   'feature_evidence', 'source_sha256', 'body'}


def receiver_from_case(case):
    """Проекция не содержит заключения, его ключа, направления или доказательства."""
    annotation = case['source_annotation']
    return {'id': case['case_id'], 'article_id': case['article_id'], 'run_id': case['run_id'],
            'primary_family': case['primary_family'], 'features': deepcopy(case['features']),
            'feature_evidence': deepcopy(annotation['feature_evidence']),
            'source_sha256': annotation['source_sha256'],
            'body': [{'key': list(case[field]['key']), 'native_key': list(case[field]['native_key']),
                      'frame': deepcopy(case[field]['frame'])} for field in ('method', 'measurement')]}


def _validate_receiver(receiver):
    require(set(receiver) == RECEIVER_FIELDS, 'Receiver contains result or unsupported fields')
    require(all(isinstance(receiver[k], str) and receiver[k] for k in
                ('id', 'article_id', 'run_id', 'primary_family', 'source_sha256')), 'Missing receiver identity')
    require(set(receiver['features']) == set(receiver['feature_evidence']) == set(AXES), 'Receiver axes differ')
    require(len(receiver['body']) == 2, 'This operator requires two distinct premises')
    require(len({tuple(b['key']) for b in receiver['body']}) == 2, 'Repeated receiver premise')
    for part in receiver['body']:
        require(set(part) == {'key', 'native_key', 'frame'} and part['native_key'][0] == receiver['article_id'],
                'Receiver premise crosses articles or contains result proof')
        frame = part['frame']
        require(frame['kind'] == 'action' and frame['action_status'] == 'performed'
                and frame['logic'] == 'single' and len(frame['statements']) == 1, 'Unsupported receiver action')
        atom = frame['statements'][0]
        require(not atom['negated'] and atom['scope']['modality'] is None and atom['scope']['quantifier'] is None,
                'Negation or modality requires a different transfer operator')
        require(len({r['role'] for r in atom['roles']}) == len(atom['roles']), 'Repeated receiver role')
    participants = [{r['role']: r['value'] for r in p['frame']['statements'][0]['roles']}
                    for p in receiver['body']]
    require(all(participants[0].get(r) is not None and participants[0].get(r) == participants[1].get(r)
                for r in ('population', 'challenge')), 'Receiver measurement belongs to another population or disease')
    for axis, value in receiver['features'].items():
        require(value is None or isinstance(value, str) and value.strip(), 'Invalid receiver feature')
        require(value is None or bool(receiver['feature_evidence'][axis]), 'Receiver feature has no evidence')


def body_shape(body):
    """Имена участников заменяются переменными с сохранением равенств между ролями."""
    variables, shape = {}, []
    for part in body:
        atom = part['frame']['statements'][0]
        roles = []
        for role in sorted(atom['roles'], key=lambda r: r['role']):
            value = role['value']
            variable = variables.setdefault(value, 'v' + str(len(variables)))
            roles.append([role['role'], variable])
        shape.append({'predicate': atom['predicate'], 'roles': roles,
                      'kind': part['frame']['kind'], 'action_status': part['frame']['action_status'],
                      'negated': atom['negated'], 'logic': part['frame']['logic']})
    return shape


def _shape(case):
    receiver = receiver_from_case(case)
    _validate_receiver(receiver)
    method_roles = {r['role']: r['value'] for r in receiver['body'][0]['frame']['statements'][0]['roles']}
    head_roles = {r['role']: r['value'] for r in case['result']['frame']['statements'][0]['roles']}
    # Относительный эффект должен принадлежать тому же явно указанному контролу.
    if method_roles.get('comparator') is None or head_roles.get('comparator') != method_roles['comparator']:
        return None
    return {'features': deepcopy(case['features']), 'body': body_shape(receiver['body']),
            'qualitative_direction': case['qualitative_direction'], 'outcome_class': case['outcome_class'],
            'head_participant_bindings': {r: {'premise': 0, 'role': r} for r in
                                          ('population', 'intervention', 'challenge', 'comparator')}}


def learn(cases, held_out_family, mode, groups):
    """Вся семья принимающего исследования исключена до просмотра заключений."""
    require(mode in MODES, 'Unknown transfer mode')
    rows, buckets, exclusions = [], defaultdict(list), Counter()
    for case in cases:
        if case['primary_family'] == held_out_family:
            exclusions['held_out_family'] += 1
            continue
        if not case['applicability_complete']:
            exclusions['unknown_axes'] += 1
            continue
        body = frozenset(tuple(case[field]['native_key']) for field in ('method', 'measurement'))
        head = tuple(case['result']['native_key'])
        if mode != 'without_dependencies' and (body, head) not in groups:
            exclusions['missing_joint_group'] += 1
            continue
        shape = _shape(case)
        if shape is None:
            exclusions['unbound_or_different_comparator'] += 1
            continue
        rows.append(case['case_id'])
        buckets[fingerprint(shape)].append((shape, case))
    rules = []
    for key, values in sorted(buckets.items()):
        families = sorted({case['primary_family'] for _, case in values})
        if len(families) < 2:
            exclusions['insufficient_independent_support'] += 1
            continue
        rules.append({'id': key, 'shape': values[0][0], 'primary_families': families,
                      'support_case_ids': sorted(c['case_id'] for _, c in values),
                      'evidence': deepcopy([c for _, c in values]),
                      'status': 'conditional_empirical_pattern', 'deductive_entailment': False})
    return rules, {'training_case_ids': rows, 'excluded': dict(exclusions)}


def apply_rules(rules, receiver):
    """Не читает результат; формирует гипотезу с полным принимающим контекстом."""
    _validate_receiver(receiver)
    candidates, rejected = [], []
    for rule in rules:
        require(rule['id'] == fingerprint(rule['shape']) and len(set(rule['primary_families'])) >= 2
                and set(rule['primary_families']) == {e['primary_family'] for e in rule['evidence']}
                and set(rule['support_case_ids']) == {e['case_id'] for e in rule['evidence']},
                'Rule has invalid independent support')
        compatibility = compare_features(rule['shape']['features'], receiver['features'])
        if not compatibility['applicable'] or rule['shape']['body'] != body_shape(receiver['body']):
            rejected.append({'rule_id': rule['id'], 'compatibility': compatibility,
                             'participant_topology_matches': rule['shape']['body'] == body_shape(receiver['body'])})
            continue
        premise = receiver['body'][0]['frame']['statements'][0]
        participants = {r['role']: r['value'] for r in premise['roles']}
        require({'population', 'intervention', 'challenge', 'comparator'} <= set(participants), 'Ungrounded transfer participant')
        candidate = {'receiver_id': receiver['id'], 'rule_id': rule['id'],
                     'status': 'conditional_empirical_hypothesis', 'deductive_entailment': False,
                     'head': {'qualitative_direction': rule['shape']['qualitative_direction'],
                              'outcome_class': rule['shape']['outcome_class'],
                              'participants': {r: participants[r] for r in ('population', 'intervention', 'challenge', 'comparator')}},
                     'receiver': deepcopy(receiver), 'support_case_ids': rule['support_case_ids'],
                     'support_families': rule['primary_families'],
                     'complete_support_contexts': [{'case_id': e['case_id'],
                         'frames': {f: deepcopy(e[f]['frame']) for f in ('method', 'measurement', 'result')}}
                         for e in rule['evidence']],
                     'transfer_obligations_ru': ['Совпадение классов не устанавливает эквивалентность опытов.',
                         'Различия доз, генотипов, контролов и расписаний требуют самостоятельной проверки.',
                         'Размер эффекта, значимость и причинность не предсказываются.']}
        candidate['id'] = fingerprint(candidate)
        candidates.append(candidate)
    return candidates, rejected


def forecast_transfers(cases, receivers, author_groups, coverage):
    """Свободная диагностика всех явных принимающих контрактов без заданного вопроса."""
    require(len({r['id'] for r in receivers}) == len(receivers), 'Repeated receiver')
    for receiver in receivers:
        _validate_receiver(receiver)
    original = set((frozenset(tuple(k) for k in body), tuple(head)) for body, head in author_groups)
    ordered = sorted(original, key=lambda g: (sorted(g[0]), g[1]))
    # Перестановка сохраняет число групп и набор заключений; посылки остаются целыми.
    permuted = {(body, ordered[(i + 1) % len(ordered)][1]) for i, (body, _) in enumerate(ordered)} if ordered else set()
    modes = {}
    for mode in MODES:
        groups = permuted if mode == 'permuted_dependencies' else original
        folds = []
        for receiver in receivers:
            rules, diagnostics = learn(cases, receiver['primary_family'], mode, groups)
            predictions, rejected = apply_rules(rules, receiver)
            require(all(receiver['primary_family'] not in c['support_families'] for c in predictions),
                    'Receiving dataset leaked into support')
            folds.append({'receiver_id': receiver['id'], 'held_out_family': receiver['primary_family'],
                          'rules': rules, 'predictions': predictions, 'rejected': rejected, **diagnostics})
        modes[mode] = folds
    return {'version': VERSION, 'question': None, 'coverage': deepcopy(coverage), 'receivers': deepcopy(receivers),
            'modes': modes, 'model_calls': 0, 'held_out_results_used_for_learning': False,
            'retrospective_annotation_and_validation_used_results': True,
            'scientific_success': False, 'graph_advantage_demonstrated': False,
            'scope_ru': 'Ретроспективная проверка явно размеченных контрактов. Остальные части перечислены '
                        'в покрытии, но не получили вымышленных контрактов. Это не полное предсказание всей карты.'}


def reapply_without_holdout(cases, receivers, author_groups):
    """Отдельная самооценка разрешает свою семью и не входит в фиксируемый прогноз."""
    groups = {(frozenset(tuple(k) for k in body), tuple(head)) for body, head in author_groups}
    rules, _ = learn(cases, None, 'graph', groups)
    candidates = []
    for receiver in receivers:
        applied, _ = apply_rules(rules, receiver)
        candidates.extend(applied)
    return {'candidates': candidates, 'is_independent_validation': False,
            'receiving_results_used_in_training': True}


def evaluate_transfers(frozen_forecast, outcomes):
    """Отдельный оценщик открывает направления только после фиксации кандидатов."""
    require(frozen_forecast['version'] == VERSION and frozen_forecast['held_out_results_used_for_learning'] is False,
            'Invalid frozen transfer')
    require(set(outcomes) == {r['id'] for r in frozen_forecast['receivers']}, 'Evaluation receivers differ')
    modes = {}
    for mode, folds in frozen_forecast['modes'].items():
        evaluated = []
        for fold in folds:
            outcome = outcomes[fold['receiver_id']]
            for candidate in fold['predictions']:
                expected = {k: candidate['head'][k] for k in ('qualitative_direction', 'outcome_class')}
                observed = {k: outcome[k] for k in expected}
                evaluated.append({'prediction_id': candidate['id'], 'receiver_id': fold['receiver_id'],
                                  'relation': 'direction_pattern_match' if expected == observed else 'direction_pattern_mismatch',
                                  'full_fact_equivalence': False, 'outcome': deepcopy(outcome)})
        modes[mode] = evaluated
    return {'version': VERSION, 'forecast_sha256': fingerprint(frozen_forecast), 'modes': modes,
            'new_scientific_knowledge_confirmed': False, 'graph_advantage_demonstrated': False,
            'expert_validated': False, 'model_calls': 0}

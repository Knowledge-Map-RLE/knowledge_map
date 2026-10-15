"""Идентификатор участника с цифрой не является переносимой числовой оценкой."""
from collections import Counter
from copy import deepcopy
from itertools import permutations
import re

from domain.article_maps import fingerprint, require
from domain.comparison_normalization import normalize_map
from domain.evidence_origin_audit import validate_origins
from domain.protocol_parameter_transfer import protocol_copy_plan, parameterize_frames, protocol_frame_identity
from domain.semantic_part_forecast import align_groups, primary_support, apply_templates
from domain.whole_map_ablation import source_neighborhood_groups, permuted_groups
from domain.whole_map_forecast import replace_terms, scoped_template, STUDY_VARIABLE, has_numeric_attributes, learn as legacy_learn

VERSION = 'whole-map-typed-participant-forecast-3'
NUMERIC_LITERAL = re.compile(r'^[+−-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+−-]?\d+)?$')


def template(body, head, plan=None):
    """Переменная копирует целый concept, включая цифры; ограничения не обобщаются."""
    variants = []
    for ordered in permutations(body):
        frames, conclusion = ([r['frame'] for r in ordered], head['frame']) if plan is None else parameterize_frames(ordered, head, plan)
        role_kinds = {}
        for frame in (*frames, conclusion):
            for s in frame['statements']:
                for role in s['roles']:
                    role_kinds.setdefault(fingerprint(role['value']), set()).add(role.get('reference_kind'))
        variables = {}
        def term(value, create):
            eligible = (isinstance(value, str) and bool(value.strip()) and not NUMERIC_LITERAL.fullmatch(value.strip())
                        and not value.startswith('knowledge:') and role_kinds[fingerprint(value)] == {'concept'})
            if not eligible: return {'constant': deepcopy(value)}
            if value not in variables:
                if not create: return {'constant': value, 'grounding': 'training_symbol'}
                variables[value] = '$' + str(len(variables))
            return {'variable': variables[value]}
        premises = [scoped_template(replace_terms(f, lambda v: term(v, True)), r['key'][0]) for r, f in zip(ordered, frames)]
        result = scoped_template(replace_terms(conclusion, lambda v: term(v, False)), head['key'][0])
        if any(s['scope']['study_group'] == STUDY_VARIABLE for s in result['statements']) and not any(
                s['scope']['study_group'] == STUDY_VARIABLE for p in premises for s in p['statements']): continue
        value = {'body': premises, 'head': result}
        variants.append((fingerprint(value), value, ordered))
    return min(variants, key=lambda v: v[0]) if variants else None


def learn(views, groups, families):
    """Поддержка относится к независимым семействам; повторения внутри статьи не суммируются."""
    buckets, rejected, rejected_groups = {}, Counter(), []
    edges = {(p, h) for body, h in groups for p in body}
    def reject(reason, body, head):
        rejected[reason] += 1; rejected_groups.append({'reason': reason, 'premises': list(body), 'head': head})
    for body, head in groups:
        require(head in views and all(p in views for p in body), 'Unknown typed-template part')
        if not 1 <= len(body) <= 3: reject('oversized_joint_group', body, head); continue
        if not all(views[k]['eligible'] for k in (*body, head)): reject('ineligible_context', body, head); continue
        if any(views[p]['frame'] == views[head]['frame'] for p in body): reject('conclusion_repeats_premise', body, head); continue
        plan = None
        if has_numeric_attributes(views[head]['frame']):
            plan = protocol_copy_plan([views[k] for k in body], views[head])
            if plan is None: reject('unmodelled_numeric_conclusion', body, head); continue
        variant = template([views[k] for k in body], views[head], plan)
        if variant is None: reject('unbound_head_participant', body, head); continue
        _, shape, ordered = variant
        shape['internal_edges'] = [(i, j) for i, a in enumerate(ordered) for j, b in enumerate(ordered) if (a['key'], b['key']) in edges]
        identity = fingerprint(shape)
        row = buckets.setdefault(identity, {'id': identity, **shape, 'families': set(), 'examples': []})
        row['families'].add(families[head[0]])
        example = {'body': [v['key'] for v in ordered], 'head': head}
        if plan is not None: example['protocol_parameter_proof'] = plan
        row['examples'].append(example)
    accepted, unsupported = [], []
    for row in buckets.values():
        row['families'] = sorted(row['families'])
        (accepted if len(row['families']) >= 2 else unsupported).append(row)
    return sorted(accepted, key=lambda r: r['id']), {'rejected': dict(rejected), 'rejected_groups': rejected_groups,
        'unsupported_templates': len(unsupported), 'unsupported_rules': sorted(unsupported, key=lambda r: r['id'])}


def structural_key(rule):
    """Только диагностика: одинаковая топология без ограничений не лицензирует правило."""
    variants = []
    for order in permutations(range(len(rule['body']))):
        variables = {}
        def alpha(value):
            if 'variable' not in value: return deepcopy(value)
            return {'variable': variables.setdefault(value['variable'], '$' + str(len(variables)))}
        body = [replace_terms(rule['body'][i], alpha) for i in order]
        head = replace_terms(rule['head'], alpha)
        for frame in (*body, head):
            for s in frame['statements']:
                s['scope'] = {'diagnostic_guard_placeholder': True}; s['attributes'] = []
                s.pop('attribute_types', None)
        inverse = {old: new for new, old in enumerate(order)}
        shape = {'body': body, 'head': head, 'internal_edges': sorted(
            [inverse[a], inverse[b]] for a, b in rule['internal_edges'])}
        variants.append((fingerprint(shape), shape))
    return min(variants, key=lambda v: v[0])


def guard_barriers(rules, views, origins):
    """Перечисляет реальные близкие структуры и все отличающиеся полные ограничения."""
    buckets = {}
    for rule in rules:
        examples, primary = [], set()
        for e in rule['examples']:
            v = views[tuple(e['head'])]; article = v['native_key'][0]
            info = origins['sources'][article]
            if info['document_kind'] == 'primary_study' and v['projection_proof']['origin']['origin'] == 'primary_result':
                primary.add(info['dataset_family']); examples.append(deepcopy(e))
        if not primary: continue
        identity, shape = structural_key(rule)
        row = buckets.setdefault(identity, {'id': identity, 'structure': shape, 'variants': [], 'primary_families': set()})
        row['primary_families'].update(primary)
        row['variants'].append({'rule_id': rule['id'], 'primary_families': sorted(primary),
            'body': deepcopy(rule['body']), 'head': deepcopy(rule['head']), 'internal_edges': deepcopy(rule['internal_edges']),
            'examples': examples})
    result = []
    for row in buckets.values():
        if len(row['primary_families']) < 2: continue
        row['primary_families'] = sorted(row['primary_families'])
        row['variants'].sort(key=lambda v: v['rule_id'])
        row.update({'status': 'structural_similarity_requires_guard_operator', 'valid_rule': False,
            'prediction_created': False, 'constraints_removed_for_inference': False})
        result.append(row)
    return sorted(result, key=lambda r: r['id'])


def forecast(frozen, maps, origin_audit):
    """Все сохранённые части и полные родители одинаковы в парном эксперименте."""
    require(frozen['run_id'] == fingerprint(frozen['binding']) and frozen['model_calls'] == 0 and frozen['target_read'] is False,
            'Invalid source forecast')
    require([fingerprint(m) for m in maps] == frozen['binding']['map_hashes'], 'Typed participant corpus differs')
    origins = validate_origins(maps, origin_audit)
    require(origins is not None, 'Complete origin audit required')
    native = {(m['article_id'], k['knowledge_id']): k for m in maps for k in m['graph']['knowledge']}
    require(len(native) == frozen['canonical_blocks'], 'Canonical coverage differs')
    views = {tuple(v['key']): deepcopy(v) for v in frozen['part_views']}
    require(len(views) == len(frozen['part_views']), 'Repeated typed part')
    by_parent = {key: [] for key in native}
    for key, v in views.items():
        v['key'], v['native_key'] = key, tuple(v['native_key'])
        proof = v['projection_proof']; parent = v['native_key']
        require(parent in native and proof['complete_native_knowledge'] == native[parent]
                and proof['view_frame_sha256'] == fingerprint(v['frame']) and v['frame']['logic'] == 'single'
                and len(v['frame']['statements']) == 1, 'Part lost its source or complete parent')
        require(proof['origin'] in origins['knowledge'][parent]['statements'], 'Part origin differs')
        by_parent[parent].append(key)
    records, groups, known = {}, [], {protocol_frame_identity(v['frame']) for v in views.values()}
    for m in maps:
        for k in normalize_map(m):
            key = (m['article_id'], k['id']); records[key] = {'provenance': [s['provenance'] for s in k['statements']]}
            groups.extend((tuple((key[0], p) for p in body), key) for body in k['premise_groups'])
            # Части нелицензированного аргумента учитываются только как уже известные, не как посылки.
            for s in k['statements']:
                atom = {name: deepcopy(s[name]) for name in ('predicate', 'roles', 'scope', 'attributes', 'negated')}
                known.add(protocol_frame_identity({'kind': k['kind'], 'action_status': k['action_status'], 'logic': 'single', 'statements': [atom]}))
    # Публикационная группировка исходного прогона и первичная поддержка — разные проверки.
    families = frozen['binding']['families']
    require(set(families) == {m['article_id'] for m in maps} and all(isinstance(v, str) and v for v in families.values()),
            'Complete sealed publication family registry required')
    choices = {'graph': groups, 'source_neighborhood_without_dependencies': source_neighborhood_groups(records),
               'permuted_dependencies': permuted_groups(records, groups)}
    policies = {}
    for policy, builder in (('legacy_digits_constant', legacy_learn), ('typed_concept_participants', learn)):
        outputs = {}
        for mode, native_groups in choices.items():
            aligned, alignment = align_groups(views, by_parent, native_groups)
            rules, learning = builder(views, aligned, families)
            accepted, support = primary_support(rules, views, origins)
            candidates, application = apply_templates(views, by_parent, accepted, native_groups, known, mode != 'source_neighborhood_without_dependencies')
            outputs[mode] = {'predictions': candidates, 'rules': accepted, 'support': support,
                'learning': learning, 'alignment': alignment, 'application': application,
                'guard_barriers': guard_barriers([*rules, *learning['unsupported_rules']], views, origins)}
            if mode == 'graph':
                flat, diagnostics = apply_templates(views, by_parent, accepted, native_groups, known, False)
                outputs['same_rules_without_dependencies'] = {'predictions': flat, 'application': diagnostics, 'same_rules': True}
        policies[policy] = outputs
    # Контроль обязан буквально воспроизвести прежнее обучение, а не только получить тот же ноль.
    baseline_reproduced = {}
    for mode, expected in frozen['learning_by_mode'].items():
        actual = policies['legacy_digits_constant'][mode]
        exact = fingerprint(actual['learning']) == fingerprint(expected['learning'])
        exact = exact and fingerprint(actual['rules']) == fingerprint(expected['primary_supported_rules'])
        require(exact, 'Legacy whole-corpus learning was not exactly reproduced')
        baseline_reproduced[mode] = exact
    digit_roles = []
    for v in views.values():
        for r in v['frame']['statements'][0]['roles']:
            if r.get('reference_kind') == 'concept' and isinstance(r['value'], str) and re.search(r'\d', r['value']):
                digit_roles.append({'part_key': list(v['key']), 'native_key': list(v['native_key']),
                    'role': r['role'], 'value': r['value'], 'pure_numeric_literal': bool(NUMERIC_LITERAL.fullmatch(r['value'].strip()))})
    return {'version': VERSION, 'question': None, 'canonical_blocks': len(native), 'semantic_statements': sum(
        len(k['semantic_frame']['statements']) for k in native.values()), 'licensed_parts': len(views),
        'parent_coverage': [{'key': list(k), 'parts': [list(p) for p in by_parent[k]]} for k in sorted(native)],
        'digit_participants': digit_roles, 'policies': policies, 'baseline_learning_reproduced': baseline_reproduced,
        'model_calls': 0, 'target_read': False,
        'future_outcomes_read': False, 'independent_future_validation': False,
        'scientific_success': False, 'graph_advantage_demonstrated': False,
        'policy_ru': 'Цифры в целиком связанном concept не равны числовому результату. Роли, кванторы, '
            'условия, время, единицы и атрибуты сохраняются. Чистый числовой литерал остаётся константой. '
            'Шаблон статистический; обобщение участника не удостоверяет перенос между популяциями. '
            'Корпус и результаты уже просмотрены: новые комбинации здесь не являются слепым будущим прогнозом.'}

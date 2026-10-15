"""Свободные шаблоны полных блоков; видимые переходы не являются причинностью."""
from copy import deepcopy
from collections import defaultdict, Counter
from itertools import permutations
import re

from domain.article_maps import fingerprint, require
from domain.comparison_normalization import normalize_map
from domain.development_prediction import validate_visible_dag
from domain.whole_map_context import audit_index, apply_context_audit
from domain.forecast_attribute_kinds import blocks_unmodelled_numeric_transfer
from domain.protocol_parameter_transfer import protocol_copy_plan, parameterize_frames, bind_parameters, instantiate_parameters, protocol_frame_identity

VERSION = 'whole-map-frame-forecast-13'
LIMITS = {'max_premises': 3, 'minimum_families': 2, 'candidate_limit': 20, 'search_steps': 200000}


def project(maps, context_audit=None):
    records, groups, coverage = {}, [], []
    audited = audit_index(maps, context_audit)
    for source in maps:
        require(source['graph']['schema_version'] == 6, 'Whole-map forecast requires schema 6')
        validate_visible_dag(source['graph'])
        originals = {k['knowledge_id']: k for k in source['graph']['knowledge']}
        for knowledge in normalize_map(source):
            key = (knowledge['article_id'], knowledge['id'])
            entry = audited.get(key)
            knowledge = apply_context_audit(knowledge, originals[knowledge['id']], entry)
            require(key not in records, 'Duplicate canonical knowledge')
            # Части аргумента и противопоставления не превращаются в независимые факты.
            frame = {'kind': knowledge['kind'], 'action_status': knowledge['action_status'],
                     'logic': knowledge['logic'], 'statements': [{
                         name: deepcopy(statement[name]) for name in ('predicate', 'roles', 'scope', 'attributes', 'negated', 'attribute_types')
                         if name in statement
                     } for statement in knowledge['statements']]}
            frame = replace_terms(frame, lambda value: value)
            reasons = []
            if any(s['unknown_context'] for s in knowledge['statements']):
                reasons.append('unknown_context_or_unresolved_reference')
            records[key] = {'key': key, 'frame': frame, 'text': knowledge['text'],
                            'run_id': knowledge['run_id'], 'eligible': not reasons,
                            'provenance': [s['provenance'] for s in knowledge['statements']]}
            for group in knowledge['premise_groups']:
                groups.append((tuple((knowledge['article_id'], p) for p in group), key))
            coverage.append({'article_id': key[0], 'knowledge_id': key[1], 'kind': frame['kind'],
                             'logic': frame['logic'], 'eligible': not reasons, 'exclusions': reasons,
                             'context_audit': entry['decision'] if entry else None})
    require(all(h in records and all(p in records for p in body) for body, h in groups), 'Unknown premise knowledge')
    return records, groups, coverage


def replace_terms(frame, operation):
    frame = deepcopy(frame)
    for s in frame['statements']:
        s['roles'] = sorted(s['roles'], key=lambda r: r['role'])
        for role in s['roles']:
            role['value'] = operation(role['value'])
    return frame


STUDY_VARIABLE = {'study_variable': '$study'}


def scoped_template(frame, article_id):
    frame = deepcopy(frame)
    for s in frame['statements']:
        scope = s['scope']
        if article_id is not None and scope['study_group'] == article_id:
            scope['study_group'] = deepcopy(STUDY_VARIABLE)
        scope['conditions'] = sorted([
            {'source_local_report': deepcopy(STUDY_VARIABLE)} if article_id is not None and c == 'source-local report: ' + article_id else c
            for c in scope['conditions']], key=fingerprint)
    return frame


def scoped_instance(frame, bindings):
    frame = deepcopy(frame)
    for s in frame['statements']:
        scope = s['scope']
        if scope['study_group'] == STUDY_VARIABLE:
            require('$study' in bindings, 'Unbound study context')
            scope['study_group'] = bindings['$study']
        scope['conditions'] = sorted([
            'source-local report: ' + bindings['$study'] if c == {'source_local_report': STUDY_VARIABLE} else c
            for c in scope['conditions']])
    return frame


def template(body, head, protocol_plan=None):
    variants = []
    for ordered in permutations(body):
        source_body, source_head = ([r['frame'] for r in ordered], head['frame']) if protocol_plan is None else parameterize_frames(ordered, head, protocol_plan)
        variables = {}
        def term(value, create):
            if not isinstance(value, str) or re.search(r'\d', value) or value.startswith('knowledge:'):
                return {'constant': value}
            if value not in variables:
                if not create:
                    # Константа из обучения не является свободной переменной.
                    # Её наличие проверяется в семантике принимающей статьи.
                    return {'constant': value, 'grounding': 'training_symbol'}
                variables[value] = '$' + str(len(variables))
            return {'variable': variables[value]}
        try:
            premises = [scoped_template(replace_terms(frame, lambda v: term(v, True)), r['key'][0]) for r, frame in zip(ordered, source_body)]
            conclusion = scoped_template(replace_terms(source_head, lambda v: term(v, False)), head.get('key', ordered[0]['key'])[0])
            head_scoped = any(s['scope']['study_group'] == STUDY_VARIABLE for s in conclusion['statements'])
            body_scoped = any(s['scope']['study_group'] == STUDY_VARIABLE for p in premises for s in p['statements'])
            if head_scoped and not body_scoped:
                continue
        except ValueError:
            continue
        value = {'body': premises, 'head': conclusion}
        variants.append((fingerprint(value), value, ordered))
    return min(variants, key=lambda x: x[0]) if variants else None


def bind(pattern, actual, existing, source_record=None):
    parameters = bind_parameters(pattern, actual, existing, source_record)
    if parameters is None: return None
    actual, bindings = parameters
    values = []
    def role_value(value):
        values.append(value)
        return None
    groups = {s['scope']['study_group'] for s in actual['statements'] if isinstance(s['scope']['study_group'], str)}
    expected_scoped = any(s['scope']['study_group'] == STUDY_VARIABLE for s in pattern['statements'])
    if expected_scoped:
        if len(groups) != 1:
            return None
        group = next(iter(groups))
        if '$study' in bindings and bindings['$study'] != group:
            return None
        bindings['$study'] = group
        actual = scoped_template(actual, group)
    else:
        actual = scoped_template(actual, None)
    shape = replace_terms(actual, role_value)
    expected = replace_terms(pattern, lambda v: None)
    if shape != expected:
        return None
    terms = [r['value'] for s in pattern['statements'] for r in sorted(s['roles'], key=lambda r: r['role'])]
    for term, value in zip(terms, values):
        if 'constant' in term:
            if term['constant'] != value:
                return None
        else:
            name = term['variable']
            if name in bindings and bindings[name] != value:
                return None
            bindings[name] = value
    return bindings


def instantiate(frame, bindings):
    return scoped_instance(instantiate_parameters(replace_terms(frame, lambda v: deepcopy(v['constant']) if 'constant' in v else bindings[v['variable']]), bindings), bindings)


def has_numeric_attributes(frame):
    return any(blocks_unmodelled_numeric_transfer(a) for s in frame['statements'] for a in s['attributes'])


def learn(records, groups, families, protocol_parameters=True):
    rules, rejected = {}, Counter()
    rejected_groups = []
    def reject(reason, body, head):
        rejected[reason] += 1
        rejected_groups.append({'reason': reason, 'premises': list(body), 'head': head})
    edges = {(p, h) for body, h in groups for p in body}
    for body, head in groups:
        if not 1 <= len(body) <= LIMITS['max_premises']:
            reject('oversized_joint_group', body, head)
            continue
        if not all(records[k]['eligible'] for k in (*body, head)):
            reject('ineligible_context', body, head)
            continue
        if any(records[p]['frame'] == records[head]['frame'] for p in body):
            reject('conclusion_repeats_premise', body, head)
            continue
        protocol_plan = None
        if has_numeric_attributes(records[head]['frame']):
            protocol_plan = protocol_copy_plan([records[k] for k in body], records[head]) if protocol_parameters else None
            if protocol_plan is None:
                reject('unmodelled_numeric_conclusion', body, head)
                continue
        variant = template([records[k] for k in body], records[head], protocol_plan)
        if variant is None:
            reject('unbound_head_participant', body, head)
            continue
        _, value, ordered = variant
        internal = [(i, j) for i, a in enumerate(ordered) for j, b in enumerate(ordered) if (a['key'], b['key']) in edges]
        value['internal_edges'] = internal
        key = fingerprint(value)
        rule = rules.setdefault(key, {'id': key, **value, 'families': set(), 'examples': []})
        rule['families'].add(families[head[0]])
        example = {'body': [r['key'] for r in ordered], 'head': head}
        if protocol_plan is not None: example['protocol_parameter_proof'] = protocol_plan
        rule['examples'].append(example)
    supported, unsupported = [], []
    for r in rules.values():
        r['families'] = sorted(r['families'])
        (supported if len(r['families']) >= LIMITS['minimum_families'] else unsupported).append(r)
    return sorted(supported, key=lambda r: r['id']), {'rejected': dict(rejected),
        'rejected_groups': rejected_groups, 'unsupported_templates': len(unsupported),
        'unsupported_rules': sorted(unsupported, key=lambda r: r['id'])}


def apply_rules(records, groups, rules, graph_mode):
    eligible = sorted((r for r in records.values() if r['eligible']), key=lambda r: r['key'])
    known = {protocol_frame_identity(r['frame']) for r in records.values()}
    joint = {frozenset(body) for body, _ in groups}
    edges = {(p, h) for body, h in groups for p in body}
    inventory = defaultdict(set)
    for r in records.values():
        for s in r['frame']['statements']:
            inventory[r['key'][0]].update(fingerprint(role['value']) for role in s['roles'])
    pool, steps, rejected = {}, 0, Counter()
    for rule in rules:
        def visit(position, bindings, premises):
            nonlocal steps
            steps += 1
            require(steps <= LIMITS['search_steps'], 'Whole-map search budget exceeded; no partial forecast published')
            if position == len(rule['body']):
                keys = [p['key'] for p in premises]
                if graph_mode and (frozenset(keys) not in joint or any((keys[a], keys[b]) not in edges for a, b in rule['internal_edges'])):
                    rejected['missing_joint_or_directed_dependency'] += 1
                    return
                if any('constant' in role['value'] and fingerprint(role['value']['constant']) not in inventory[keys[0][0]]
                       for s in rule['head']['statements'] for role in s['roles']):
                    rejected['head_constant_not_grounded_in_receiving_source'] += 1
                    return
                frame = instantiate(rule['head'], bindings)
                identity = fingerprint(frame)
                semantic_identity = protocol_frame_identity(frame)
                if semantic_identity in known:
                    rejected['known_conclusion'] += 1
                    return
                candidate = {'id': identity, 'frame': frame, 'status': 'empirical_template_hypothesis',
                             'rule_id': rule['id'], 'support_families': rule['families'],
                             'premises': [{'article_id': p['key'][0], 'knowledge_id': p['key'][1],
                                           'run_id': p['run_id'], 'text': p['text'], 'provenance': p['provenance']} for p in premises],
                             'logical_entailment': False, 'causality_asserted': False}
                candidate['entity_grounding'] = 'bound variables and training constants present in receiving article'
                prior = pool.get(semantic_identity)
                if prior is None or (-len(candidate['support_families']), candidate['rule_id']) < (-len(prior['support_families']), prior['rule_id']):
                    pool[semantic_identity] = candidate
                return
            for r in eligible:
                if r in premises:
                    continue
                # Области исследования не объединяются через одинаковые названия участников.
                if premises and r['key'][0] != premises[0]['key'][0]:
                    continue
                bound = bind(rule['body'][position], r['frame'], bindings, r)
                if bound is not None:
                    visit(position + 1, bound, [*premises, r])
        visit(0, {}, [])
    ranked = sorted(pool.values(), key=lambda c: (-len(c['support_families']), len(c['premises']), c['id']))
    return ranked[:LIMITS['candidate_limit']], {'pool': len(ranked), 'search_steps': steps, 'rejected': dict(rejected)}


def forecast_records(records, groups, families):
    from domain.whole_map_ablation import source_neighborhood_groups, permuted_groups, known_baselines, VERSION as ABLATION_VERSION
    rules, learning = learn(records, groups, families)
    modes, diagnostics = {}, {}
    for mode in ('graph', 'same_rules_without_dependencies'):
        modes[mode], diagnostics[mode] = apply_rules(records, groups, rules, mode == 'graph')
    control_groups = {'source_neighborhood_without_dependencies': source_neighborhood_groups(records),
                      'permuted_dependencies': permuted_groups(records, groups)}
    control_learning = {}
    for mode, controls in control_groups.items():
        learned, rejected = learn(records, controls, families)
        control_learning[mode] = {'rules': learned, 'learning': rejected, 'groups': len(controls)}
        modes[mode], diagnostics[mode] = apply_rules(records, controls, learned, mode == 'permuted_dependencies')
    baseline, baseline_diagnostic = known_baselines(records, families, LIMITS['candidate_limit'])
    modes.update(baseline)
    diagnostics['known_baselines'] = baseline_diagnostic
    return {'version': VERSION, 'question': None, 'limits': LIMITS,
            'canonical_blocks': len(records), 'joint_groups': len(groups), 'rules': rules,
            'learning': learning, 'predictions': modes, 'diagnostics': diagnostics,
            'structure_controls_version': ABLATION_VERSION, 'control_learning': control_learning,
            'control_policy': {'source_neighborhood': 'up to three preceding canonical blocks within the same source unit; no DAG',
                               'permutation': 'deterministic within-source graph-label permutation; topology preserved',
                               'candidate_budget': LIMITS['candidate_limit'], 'target_used': False},
            'head_constant_policy': 'training-grounded symbols require occurrence in receiving-source semantic roles; no entity invention',
            'factor_whitelist': None, 'predicate_whitelist': None,
            'graph_advantage_demonstrated': False, 'expert_validated': False, 'model_calls': 0,
            'support_note': 'Explicit provenance families; scientific independence requires a separate audit'}


def forecast(maps, families, context_audit=None, model_audit=None, origin_audit=None, categorical_licenses=None):
    from domain.whole_map_numeric import project_numeric
    from domain.whole_map_provenance import partition_provenance
    require(set(families) == {m['article_id'] for m in maps}, 'Explicit provenance families required')
    from domain.evidence_origin_audit import validate_origins, audit_rule_support
    origin_index = validate_origins(maps, origin_audit)
    records, groups, coverage = project(maps, context_audit)
    # Старое представление проверяется на том же корпусе; оно не подменяет новую публикацию.
    previous = forecast_records(records, groups, families)
    from domain.statistical_context_audit import audit_models
    model_index = audit_models(maps, model_audit)
    for key, entry in model_index.items():
        records[key]['model_context'] = entry
    partitioned, provenance = partition_provenance(records, families)
    projected, numerical = project_numeric(partitioned)
    result = forecast_records(projected, groups, families)
    result['evidence_origin_support'] = {
        'supported_rules': audit_rule_support(result['rules'], origin_index),
        'unsupported_rules': audit_rule_support(result['learning']['unsupported_rules'], origin_index),
        'policy': 'Source attribution is diagnostic; no candidate is certified as an empirical prediction or logical entailment by origin counts alone.'}
    from domain.whole_map_categorical import infer
    result['categorical_inference'] = infer(records, groups)
    from domain.categorical_licenses import licensed_inference
    result['licensed_categorical_inference'] = licensed_inference(maps, records, groups, categorical_licenses)
    result['coverage'] = coverage
    result['numeric_consequences'] = numerical
    result['provenance_partition'] = provenance
    result['representation_comparison'] = {
        'full_numeric_frames': {'rules': len(previous['rules']), 'learning': previous['learning'],
                                'candidates': {mode: len(rows) for mode, rows in previous['predictions'].items()}},
        'qualitative_views': {'rules': len(result['rules']), 'learning': result['learning'],
                             'candidates': {mode: len(rows) for mode, rows in result['predictions'].items()}},
        'graph_advantage_demonstrated': False}
    return result

"""Чувствительность поддержки шаблонов: диагностическое сближение не лицензирует вывод."""
from collections import defaultdict
from copy import deepcopy
from itertools import permutations

from domain.article_maps import fingerprint, require
from domain.operator_frame_routing import PREDICATES, VERSION as ROUTING_VERSION

VERSION = 'whole-map-rule-support-diagnostic-2'
MODES = {
    'exact': set(),
    'attribute_values_hidden': {'attributes'},
    'context_details_hidden': {'context'},
    'predicate_family_only': {'predicate'},
    'role_constants_abstracted': {'roles'},
    'attributes_and_context_hidden': {'attributes', 'context'},
    'attributes_context_and_roles_hidden': {'attributes', 'context', 'roles'},
    'all_diagnostic_fields_hidden': {'attributes', 'context', 'roles', 'predicate'},
}


def diagnostic_shape(rule, mode):
    require(mode in MODES and 1 <= len(rule['body']) <= 3, 'Explicit bounded diagnostic mode required')
    changes = MODES[mode]
    if not changes:
        return fingerprint({key: rule[key] for key in ('body', 'head', 'internal_edges')})
    shapes = []
    for order in permutations(range(len(rule['body']))):
        names = {}; constants = {}
        def frame(source, is_head):
            value = deepcopy(source)
            for s in value['statements']:
                if 'predicate' in changes:
                    # Неизвестные предикаты сохраняются, а не подставляются в универсальное семейство.
                    s['predicate'] = 'diagnostic-family:' + PREDICATES[s['predicate']] if s['predicate'] in PREDICATES else s['predicate']
                if 'attributes' in changes:
                    for attr in s['attributes']:
                        attr['value'] = {'diagnostic_value_hidden': True}
                if 'context' in changes:
                    # Полярность, квантор и модальность остаются различимыми даже в опасной диагностике.
                    for key in ('population', 'time', 'place', 'conditions'):
                        s['scope'][key] = {'diagnostic_context_hidden': key}
                for role in sorted(s['roles'], key=lambda r: r['role']):
                    term = role['value']
                    if 'variable' in term:
                        name = term['variable']
                        if name not in names: names[name] = '$' + str(len(names))
                        role['value'] = {'variable': names[name]}
                    elif 'roles' in changes:
                        identity = fingerprint(term['constant'])
                        if identity not in constants:
                            constants[identity] = ('head_only_' if is_head else 'body_') + str(len(constants))
                        role['value'] = {'diagnostic_constant_identity': constants[identity]}
            return value
        body = [frame(rule['body'][i], False) for i in order]
        head = frame(rule['head'], True)
        positions = {old: new for new, old in enumerate(order)}
        edges = sorted([positions[a], positions[b]] for a, b in rule['internal_edges'])
        shapes.append(fingerprint({'body': body, 'head': head, 'internal_edges': edges}))
    return min(shapes)


def diagnose_support(artifact):
    require(artifact['question'] is None and artifact['model_calls'] == 0, 'Explicit model-free whole-map forecast required')
    rules = [*artifact['rules'], *artifact['learning']['unsupported_rules']]
    require(len({r['id'] for r in rules}) == len(rules), 'Repeated learned template')
    require(all(diagnostic_shape(r, 'exact') == r['id'] for r in rules), 'Template binding changed')
    require(len(artifact['coverage']) == artifact['canonical_blocks'], 'Whole-map coverage changed')
    origin = artifact['evidence_origin_support']
    require(origin['supported_rules']['status'] == origin['unsupported_rules']['status'] == 'source_origins_declared',
            'Explicit source-origin audit required')
    origin_rows = [*origin['supported_rules']['rules'], *origin['unsupported_rules']['rules']]
    require({r['rule_id'] for r in origin_rows} == {r['id'] for r in rules}, 'Origin support differs from templates')
    index = {row['rule_id']: row for row in origin_rows}
    require(len(index) == len(origin_rows), 'Repeated origin support row')
    minimum = artifact['limits']['minimum_families']
    modes = {}
    for mode in MODES:
        groups = defaultdict(list)
        for rule in rules: groups[diagnostic_shape(rule, mode)].append(rule)
        rows = []
        for shape, members in sorted(groups.items()):
            publications = sorted({f for r in members for f in r['families']})
            primary = sorted({f for r in members for f in index[r['id']]['declared_primary_dataset_families']})
            secondary = sorted({f for r in members for f in index[r['id']]['secondary_sources']})
            rows.append({'shape_id': shape, 'rule_ids': sorted(r['id'] for r in members),
                'publication_families': publications, 'declared_primary_dataset_families': primary,
                'secondary_sources': secondary, 'at_least_two_publication_families': len(publications) >= minimum,
                'at_least_two_declared_primary_families': len(primary) >= minimum,
                'examples': [deepcopy(e) for r in members for e in r['examples']],
                'inference_licensed': False, 'context_equivalence_established': False,
                'interpretation_ru': 'Диагностическое сходство формы; потерянные значения и контексты запрещают считать его правилом.'})
        modes[mode] = {'groups': rows, 'shape_count': len(rows),
            'multi_publication_shape_count': sum(r['at_least_two_publication_families'] for r in rows),
            'multi_primary_shape_count': sum(r['at_least_two_declared_primary_families'] for r in rows)}
    exact = modes['exact']['multi_publication_shape_count']
    require(exact == len(artifact['rules']), 'Exact support diagnostic differs from forecaster')
    predictions = artifact['predictions']
    return {'version': VERSION, 'routing_version': ROUTING_VERSION,
        'canonical_blocks': artifact['canonical_blocks'], 'template_count': len(rules), 'supported_exact_rules': exact,
        'learning_rejections': deepcopy(artifact['learning']['rejected']),
        'learning_rejected_groups': deepcopy(artifact['learning']['rejected_groups']),
        'modes': modes, 'complete_original_templates': deepcopy(rules),
        'coverage': deepcopy(artifact['coverage']), 'model_calls': 0, 'predictions': [],
        'joint_gate_removal_cannot_help_with_no_rules': exact == 0,
        'observed_same_rules_candidates_with_gate': len(predictions['graph']),
        'observed_same_rules_candidates_without_gate': len(predictions['same_rules_without_dependencies']),
        'scientific_success': False, 'graph_advantage_demonstrated': False,
        'policy_ru': 'Только диагностика обученных шаблонов. Отброшенные группы остаются в отчёте; их заключения не додумываются. '
                     'Скрытие контекста или значений не разрешено в генерации. Число публикаций не удостоверяет независимость.'}

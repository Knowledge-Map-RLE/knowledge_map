"""Маски шаблонов выявляют причины несовпадения, но не допускают научный перенос."""
from collections import Counter, defaultdict
from copy import deepcopy
from itertools import permutations

from domain.article_maps import fingerprint, require

VERSION = 'unsupported-template-context-diagnostics-1'
MASKS = ('exact', 'context', 'attributes', 'context_and_attributes', 'relation_shape')


def diagnostic_signature(rule, mask):
    require(mask in MASKS, 'Unknown diagnostic mask')
    require(1 <= len(rule['body']) <= 3, 'Diagnostic premise budget exceeded')
    candidates = []
    for order in permutations(range(len(rule['body']))):
        frames = [deepcopy(rule['body'][i]) for i in order] + [deepcopy(rule['head'])]
        variables = {}
        for frame in frames:
            for s in frame['statements']:
                if mask in {'context', 'context_and_attributes', 'relation_shape'}:
                    # Маска — только диагностический эксперимент, не утверждение равенства.
                    for key in ('time', 'conditions', 'study_group'): s['scope'][key] = {'diagnostically_masked': key}
                if mask in {'attributes', 'context_and_attributes', 'relation_shape'}: s['attributes'] = []
                for role in s['roles']:
                    value = role['value']
                    if mask == 'relation_shape': role['value'] = {'diagnostically_masked': 'entity_identity'}
                    elif isinstance(value, dict) and 'variable' in value:
                        old = value['variable']
                        role['value'] = {**value, 'variable': variables.setdefault(old, '$' + str(len(variables)))}
                s['roles'] = sorted(s['roles'], key=lambda r: r['role'])
        indices = {old: new for new, old in enumerate(order)}
        edges = sorted((indices[a], indices[b]) for a, b in rule['internal_edges'])
        candidates.append(fingerprint({'body': frames[:-1], 'head': frames[-1], 'internal_edges': edges}))
    return min(candidates)


def audit_templates(artifact, mode='graph'):
    require(artifact['question'] is None and artifact['model_calls'] == 0 and artifact['target_read'] is False,
            'Source-only sealed forecast required for diagnostics')
    learning = artifact['learning_by_mode'][mode]
    require(not learning['primary_supported_rules'], 'This audit describes the unsupported-rule stage')
    rules = learning['learning']['unsupported_rules']
    support = {row['rule_id']: row for row in learning['unsupported_origin_support']}
    require(set(support) == {r['id'] for r in rules}, 'Exact unsupported-rule origin support required')
    primary = [r for r in rules if support[r['id']]['primary_families']]
    levels = []
    for mask in MASKS:
        groups = defaultdict(list)
        for r in primary: groups[diagnostic_signature(r, mask)].append(r)
        clusters = []
        for identity, members in sorted(groups.items()):
            families = sorted({f for r in members for f in support[r['id']]['primary_families']})
            if len(families) < 2: continue
            clusters.append({'id': identity, 'rule_ids': sorted(r['id'] for r in members),
                'primary_families': families, 'transfer_licensed': False, 'logical_entailment': False})
        levels.append({'mask': mask, 'distinct_groups': len(groups), 'cross_primary_clusters': clusters,
            'masked_groups_are_forecasts': False, 'rules_admitted': 0})
    rows = []
    for r in primary:
        rows.append({'rule_id': r['id'], 'primary_families': support[r['id']]['primary_families'],
            'body_predicates': [[s['predicate'] for s in frame['statements']] for frame in r['body']],
            'head_predicates': [s['predicate'] for s in r['head']['statements']],
            'all_premises_performed_actions': all(f['kind'] == 'action' and f['action_status'] == 'performed' for f in r['body']),
            'examples': deepcopy(support[r['id']]['examples']), 'deductive_rule': False})
    return {'version': VERSION, 'source_run_id': artifact['run_id'], 'mode': mode,
        'unsupported_templates': len(rules), 'templates_with_primary_support': len(primary),
        'primary_family_template_counts': dict(Counter(f for r in primary for f in support[r['id']]['primary_families'])),
        'all_action_premise_templates': sum(r['all_premises_performed_actions'] for r in rows),
        'levels': levels, 'primary_templates': rows, 'model_calls': 0, 'target_read': False,
        'new_rules': 0, 'new_predictions': 0, 'scientific_success': False,
        'policy_ru': 'Маски показывают структуру несовпадений. Удалённые ими условия, числа и тождества '
            'не объявляются взаимозаменяемыми и не используются для генерации. Выполненный метод '
            'может быть необходим для получения результата, но сам по себе не гарантирует его направление.'}

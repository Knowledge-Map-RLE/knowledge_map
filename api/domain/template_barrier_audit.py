"""Диагностика расхождения шаблонов; ослабления не являются правилами вывода."""
from collections import Counter, defaultdict
from copy import deepcopy
from itertools import permutations
import re

from domain.article_maps import fingerprint, require

VERSION = 'whole-map-template-barrier-audit-1'
POLICIES = ('exact', 'source_labels', 'without_context', 'relational_structure', 'predicate_topology')
POLICY_RU = {
    'exact': 'Полный действующий шаблон',
    'source_labels': 'Диагностическое удаление обозначений источника',
    'without_context': 'Дополнительно удалены все условия и атрибуты',
    'relational_structure': 'Дополнительно обобщены константы участников с сохранением их связности',
    'predicate_topology': 'Только предикаты, виды знаний и структура зависимостей',
}


def _shape(rule, policy, article_ids):
    """Сохраняет оригинал; даже совпадение максимально ослабленной формы не допускает прогноз."""
    value = deepcopy({k: rule[k] for k in ('body', 'head', 'internal_edges')})
    if policy == 'exact':
        return value
    # Префикс серии опыта может упоминать целевую статью; PMCID источника — последний в его id.
    pmcids = [matches[-1] for article in article_ids if (matches := re.findall(r'pmc\d+', article, re.I))]
    labels = sorted(set(article_ids) | set(pmcids), key=lambda s: -len(s))

    def source_label(text):
        if not isinstance(text, str):
            return text
        for label in labels:
            text = re.sub(r'(?<![\w])' + re.escape(label) + r'(?![\w])', '<source>', text, flags=re.I)
        return text

    for frame in [*value['body'], value['head']]:
        for statement in frame['statements']:
            for role in statement['roles']:
                if isinstance(role['value'], dict) and 'constant' in role['value']:
                    role['value']['constant'] = source_label(role['value']['constant'])
            if policy == 'source_labels':
                # Это верхняя диагностическая граница, а не разрешение стереть биологическое время.
                statement['scope'] = {
                    k: [source_label(x) for x in v] if isinstance(v, list) else source_label(v)
                    for k, v in statement['scope'].items()}
                t = statement['scope'].get('time')
                if isinstance(t, str) and re.fullmatch(r'own experimental report in \d{4}', t):
                    statement['scope']['time'] = '<publication-label>'
            else:
                statement.pop('scope', None)
                statement.pop('attributes', None)
                statement.pop('attribute_types', None)
                if policy == 'predicate_topology':
                    statement.pop('roles', None)
    return value


def signature(rule, policy, article_ids):
    require(policy in POLICIES, 'Unknown diagnostic policy')
    value = _shape(rule, policy, article_ids)
    variants = []
    # Перестановка совместных посылок и альфа-переименование не зависят от исходного хеша.
    for order in permutations(range(len(value['body']))):
        candidate = deepcopy(value)
        candidate['body'] = [candidate['body'][i] for i in order]
        positions = {old: new for new, old in enumerate(order)}
        candidate['internal_edges'] = sorted([[positions[a], positions[b]] for a, b in value['internal_edges']])
        symbols = {}
        for frame in [*candidate['body'], candidate['head']]:
            for statement in frame['statements']:
                for role in sorted(statement.get('roles', []), key=lambda r: r['role']):
                    term = role['value']
                    if isinstance(term, dict) and 'variable' in term:
                        identity = ('variable', term['variable'])
                    elif policy == 'relational_structure':
                        identity = ('constant', fingerprint(term))
                    else:
                        continue
                    symbols.setdefault(identity, '$' + str(len(symbols)))
                    role['value'] = {'variable': symbols[identity]}
                if 'roles' in statement:
                    statement['roles'] = sorted(statement['roles'], key=lambda r: r['role'])
        variants.append(fingerprint(candidate))
    require(bool(variants), 'Diagnostic template has no body')
    return min(variants)


def analyze(artifact):
    require(artifact['run_id'] == fingerprint(artifact['binding']), 'Input forecast seal differs')
    require(artifact['question'] is None and artifact['target_read'] is False and artifact['model_calls'] == 0,
            'Question, target or model access is incompatible with this audit')
    ids = [r['article_id'] for r in artifact['binding']['references']]
    require(len(ids) == len(set(ids)), 'Repeated source identity')
    views = {tuple(v['key']): v for v in artifact['part_views']}
    require(len(views) == len(artifact['part_views']), 'Duplicate part view')
    for v in views.values():
        proof = v['projection_proof']
        require(v['key'][0] in ids and v['native_key'][0] == v['key'][0]
                and proof['parent_key'] == v['native_key'] and proof['run_id'] == v['run_id']
                and proof['view_frame_sha256'] == fingerprint(v['frame'])
                and proof['parent_knowledge_sha256'] == fingerprint(proof['complete_native_knowledge']),
                'Diagnostic part provenance differs')
    modes = {}
    for mode, learned in artifact['learning_by_mode'].items():
        rules = [*learned['publication_supported_rules'], *learned['learning']['unsupported_rules']]
        require(len({r['id'] for r in rules}) == len(rules), 'Duplicate diagnostic rule')
        support = {r['rule_id']: r for r in [*artifact['primary_support_by_mode'][mode], *learned['unsupported_origin_support']]}
        require(set(support) == {r['id'] for r in rules}, 'Missing origin support')
        primary = []
        witnesses = {}
        for rule in rules:
            witnesses[rule['id']] = []
            require(rule['id'] == fingerprint({k: rule[k] for k in ('body', 'head', 'internal_edges')}), 'Rule identity differs')
            for example in support[rule['id']]['examples']:
                require(tuple(example['part_head']) in views, 'Unknown diagnostic witness')
                v = views[tuple(example['part_head'])]
                require(v['native_key'] == example['native_head'] and v['projection_proof']['origin']['origin'] == example['origin'],
                        'Witness origin differs')
                if example['origin'] == 'primary_result' and example['declared_primary_family'] is not None:
                    witnesses[rule['id']].append(deepcopy(example))
            if witnesses[rule['id']]:
                primary.append(rule)
        policies = {}
        for policy in POLICIES:
            buckets = defaultdict(list)
            for rule in primary:
                buckets[signature(rule, policy, ids)].append(rule['id'])
            collisions = []
            for key, members in sorted(buckets.items()):
                evidence = [w for rid in members for w in witnesses[rid]]
                families = sorted({w['declared_primary_family'] for w in evidence})
                if len(families) >= 2:
                    unique = {fingerprint(w): w for w in evidence}
                    collisions.append({'signature': key, 'rule_ids': sorted(members), 'primary_families': families,
                        'witnesses': sorted(unique.values(), key=fingerprint), 'valid_inference': False,
                        'scientific_equivalence': False, 'new_prediction': False})
            policies[policy] = {'label_ru': POLICY_RU[policy], 'distinct_shapes': len(buckets),
                'multi_family_collision_groups': len(collisions), 'collision_groups': collisions}
        predicate_buckets = defaultdict(list)
        for rule in primary:
            pattern = {'body': sorted([(s['predicate'], s['negated']) for frame in rule['body'] for s in frame['statements']]),
                       'head': [(s['predicate'], s['negated']) for s in rule['head']['statements']]}
            predicate_buckets[fingerprint(pattern)].append((rule, pattern))
        predicate_patterns = []
        for key, members in sorted(predicate_buckets.items()):
            evidence = [w for r, _ in members for w in witnesses[r['id']]]
            predicate_patterns.append({'signature': key, 'pattern': members[0][1],
                'rule_ids': sorted(r['id'] for r, _ in members),
                'primary_families': sorted({w['declared_primary_family'] for w in evidence}),
                'valid_inference': False})
        modes[mode] = {'total_templates': len(rules), 'primary_result_templates': len(primary),
            'primary_sources': sorted({w['native_head'][0] for r in primary for w in witnesses[r['id']]}),
            'policies': policies, 'predicate_patterns': predicate_patterns,
            'multi_family_predicate_patterns': sum(len(p['primary_families']) >= 2 for p in predicate_patterns)}
    return {'version': VERSION, 'input_run_id': artifact['run_id'], 'canonical_blocks': artifact['canonical_blocks'],
        'licensed_parts': artifact['licensed_parts'], 'modes': modes, 'new_predictions': 0,
        'source_predictions': {m: len(p) for m, p in artifact['predictions'].items()},
        'scientific_success': False, 'graph_advantage_demonstrated': False, 'model_calls': 0, 'target_read': False,
        'policy_ru': 'Ослабленные формы служат только диагностике. Совпадение после удаления условий или участников '
                     'не удостоверяет эквивалентность, причинность, допустимое правило либо новый прогноз. '
                     'Исходные шаблоны и научные ограничения сохранены в неизменяемом входном снимке.'}

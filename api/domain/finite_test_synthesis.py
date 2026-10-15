"""Синтез конечного списка тестов не утверждает отсутствие биологического эффекта."""
from collections import Counter, defaultdict, deque
from copy import deepcopy
from hashlib import sha256

from domain.article_maps import ArticleMapError, fingerprint, require
from domain.author_argument_circuits import VERSION as CIRCUIT_VERSION
from domain.quantified_evidence_reasoning import parse_reported_operand, reason_over_quantified_evidence

VERSION = 'source-bound-variadic-finite-test-synthesis-2'


def _cohort(statement):
    roles = [r['target'] for r in statement['roles'] if r['role'] == 'cohort']
    return roles[0] if len(roles) == 1 else None


def _threshold(parent, statements, graph):
    """Порог разрешён только собственным явным определением, без значения по умолчанию."""
    if parent['complete_parent']['kind'] != 'state' or not statements:
        return None
    definitions = []
    for s in statements:
        if (s['predicate'] != 'define multiplicity threshold' or s['unknown_context']
                or s['negated'] or s['scope']['modality'] is not None or _cohort(s) is None):
            return None
        attrs = s['original_statement']['qualifiers']['attributes']
        alphas = [a for a in attrs if a['name'] == 'alpha']
        comparisons = [a for a in attrs if a['name'] == 'comparison']
        if (len(alphas) != 1 or alphas[0]['unit'] != 'dimensionless' or len(comparisons) != 1
                or comparisons[0]['value'] != 'strict p<alpha'):
            return None
        try:
            op, cutoff = parse_reported_operand(alphas[0]['value'])
        except ArticleMapError:
            return None
        if op is not None or cutoff <= 0:
            return None
        evidence = [_evidence(graph, eid, parent) for eid in s['evidence']]
        require(evidence, 'Threshold definition lacks source evidence')
        definitions.append({'statement_id': s['statement_id'], 'cohort': _cohort(s),
                            'cutoff': str(cutoff.normalize()), 'scope': deepcopy(s['scope']), 'evidence': evidence})
    return definitions


def _evidence(graph, eid, parent):
    require(eid in graph['source_units'], 'Unknown finite-set source unit')
    e = graph['source_units'][eid]
    require(e['article_id'] == parent['article_id'] and e['source_sha256'] == parent['source_sha256']
            and sha256(e['text'].encode()).hexdigest() == e['sha256']
            and len(e['text']) == e['end'] - e['start'], 'Finite-set evidence changed')
    return deepcopy(e)


def _index(graph, quantitative):
    statements = defaultdict(list)
    for s in graph['statements'].values():
        statements[s['parent']].append(s)
    proofs = {p['parent']: p for p in quantitative['proofs']}
    coverage = {p['parent']: p for p in quantitative['coverage']}
    result = {}
    for pid, parent in graph['parents'].items():
        parts = sorted(statements[pid], key=lambda s: s['position'])
        complete = all(r['status'] == 'printed_comparison_computed'
                       for r in coverage[pid]['all_statement_decisions'])
        if complete and pid in proofs and all(_cohort(s) is not None for s in parts):
            result[pid] = {'kind': 'measured_tests', 'proof': proofs[pid], 'statements': parts}
        else:
            threshold = _threshold(parent, parts, graph)
            result[pid] = {'kind': 'threshold_definition' if threshold else 'unsupported_full_parent',
                           'definitions': threshold, 'statements': parts,
                           'all_statement_decisions': coverage[pid]['all_statement_decisions']}
    return result


def _exact_analysis_scope(statement):
    """Идентичность измерения без подмены различий между участниками и исходами."""
    roles = sorted((r['role'], r['target']) for r in statement['roles']
                   if r['role'] not in {'cohort', 'adjustment'})
    original = statement['original_statement']
    return fingerprint({
        'roles': roles,
        'scope': statement['scope'],
        'quantifier': original['quantifier'],
        'temporal_context': original['temporal_context'],
        'negated': statement['negated'],
        'unknown_context': statement['unknown_context'],
    })


def synthesize_finite_set(graph, indexed, members):
    """Вся заданная группа используется целиком; неизвестные части не отбрасываются."""
    require(isinstance(members, list) and bool(members), 'Nonempty explicit finite member set required')
    require(len(members) == len(set(members)) and all(p in indexed for p in members),
            'Unknown or repeated canonical finite-set member')
    articles = {graph['parents'][p]['article_id'] for p in members}
    require(len(articles) == 1, 'Finite synthesis cannot merge source-local cohorts')
    member_audit = [{'parent': p, 'kind': indexed[p]['kind'],
                     'all_statement_decisions': deepcopy(indexed[p].get('all_statement_decisions',
                                                 indexed[p].get('proof', {}).get('all_statement_decisions', [])))}
                    for p in members]
    if any(indexed[p]['kind'] == 'unsupported_full_parent' for p in members):
        return {'status': 'unsupported_member_in_complete_group', 'member_audit': member_audit, 'summary': None}
    tests, definitions = [], []
    for pid in sorted(members):
        item = indexed[pid]
        if item['kind'] == 'threshold_definition':
            definitions.extend({'parent': pid, **deepcopy(d)} for d in item['definitions'])
            continue
        proof = item['proof']
        for s, operation in zip(item['statements'], proof['operations']):
            require(s['statement_id'] == operation['statement_id'], 'Complete test vector order changed')
            _, cutoff = parse_reported_operand(operation['operation']['reported_alpha'])
            tests.append({'parent': pid, 'statement_id': s['statement_id'], 'proof_id': proof['id'],
                          'cohort': _cohort(s), 'cutoff': str(cutoff.normalize()), 'predicate': s['predicate'],
                          'original_statement': deepcopy(s['original_statement']),
                          'operation': deepcopy(operation)})
    if not tests:
        return {'status': 'no_measured_tests', 'member_audit': member_audit, 'summary': None}
    cohorts = {t['cohort'] for t in tests}; cutoffs = {t['cutoff'] for t in tests}
    if len(cohorts) != 1 or len(cutoffs) != 1 or any(d['cohort'] not in cohorts or d['cutoff'] not in cutoffs for d in definitions):
        return {'status': 'incompatible_cohort_or_explicit_threshold', 'member_audit': member_audit, 'summary': None}
    counts = Counter(t['operation']['operation']['decision'] for t in tests)
    below, unresolved = counts['below'], counts['undetermined']; total = len(tests)
    profile = {'listed_tests': total, 'below': below, 'not_below': counts['not_below'], 'undetermined': unresolved,
               'passing_count_lower_bound': below, 'passing_count_upper_bound': below + unresolved,
               'none_of_listed_tests_below': below == 0 and unresolved == 0,
               'all_of_listed_tests_below': below == total,
               'at_least_one_listed_test_below': below > 0}
    summary = {'predicate': 'finite reported test set threshold profile', 'article_id': next(iter(articles)),
               'members': sorted(members), 'cohort': next(iter(cohorts)), 'cutoff': next(iter(cutoffs)),
               'tests': tests, 'threshold_definitions': definitions, 'profile': profile,
               'whole_parents': {p: deepcopy(graph['parents'][p]) for p in sorted(members)},
               'independent_tests_assumed': False, 'compound_parts_asserted_as_independent_facts': False,
               'biological_effect_or_absence_established': False, 'causal_effect_established': False,
               'finite_set_only': True, 'new_empirical_prediction': False,
               'threshold_definition_essential_when_each_test_already_has_alpha': False}
    summary['id'] = fingerprint(summary)
    return {'status': 'finite_profile_computed', 'member_audit': member_audit, 'summary': summary}


def _groups(graph, circuits):
    require(circuits['version'] == CIRCUIT_VERSION and circuits['canonical_blocks'] == len(graph['parents'])
            and set(circuits['nodes']) == set(graph['visible_occurrences']), 'Full circuit snapshot required')
    groups = []
    for gid, group in sorted(circuits['groups'].items()):
        require(gid == group['id'] == fingerprint({k: v for k, v in group.items() if k != 'id'}),
                'Finite author group changed')
        members = group['premises']; occurrences = group['premise_occurrences']; head = group['head']
        require(bool(members) and len(members) == len(occurrences) and len(set(occurrences)) == len(occurrences)
                and head in graph['parents'] and group['head_occurrence'] in circuits['nodes'], 'Incomplete finite author group')
        require(len(members) == len(set(members)), 'Repeated canonical group member needs separate normalization')
        for pid, oid in [(head, group['head_occurrence']), *zip(members, occurrences)]:
            require(pid in graph['parents'] and oid in circuits['nodes']
                    and circuits['nodes'][oid]['parent'] == graph['visible_occurrences'][oid]['parent'] == pid,
                    'Finite group occurrence differs')
            parent = graph['parents'][pid]
            require(parent['article_id'] == group['article_id'] and parent['source_sha256'] == group['source_sha256']
                    and parent['graph_sha256'] == group['graph_sha256'], 'Cross-source finite author group')
        require(group['connective'] == 'all_members_required_by_this_author_group'
                and not group['alternative_groups_are_jointly_required'] and not group['deductive_rule']
                and not group['causal_rule'], 'Author group is not a mathematical rule')
        for e in group['evidence']:
            require(e == _evidence(graph, e['id'], graph['parents'][head]), 'Finite transition evidence differs')
        groups.append(group)
    # Полнота проверяется по исходному списку, без чтения текста заключения как входа операции.
    require(len(groups) == len(graph['author_dependencies']), 'Finite group coverage differs')
    signatures = lambda rows: Counter((r['head'], tuple(r['premises']), r['head_occurrence'],
                                      tuple(r['premise_occurrences'])) for r in rows)
    native_groups = [{'head': d['conclusion'], 'premises': d['premises'], 'head_occurrence': d['conclusion_occurrence'],
                      'premise_occurrences': d['premise_occurrences']} for d in graph['author_dependencies']]
    require(signatures(groups) == signatures(native_groups), 'Finite group membership differs from native dependencies')
    expected = {(o, g['head_occurrence']) for g in groups for o in g['premise_occurrences']}
    require(expected == {(e['source'], e['target']) for e in graph['visible_occurrence_edges']},
            'Finite group edges differ from native DAG')
    adjacency = defaultdict(set); indegree = {o: 0 for o in circuits['nodes']}
    for start, end in expected:
        adjacency[start].add(end); indegree[end] += 1
    queue = deque(o for o, n in indegree.items() if n == 0); visited = 0
    while queue:
        oid = queue.popleft(); visited += 1
        for end in adjacency[oid]:
            indegree[end] -= 1
            if indegree[end] == 0:
                queue.append(end)
    require(visited == len(indegree), 'Finite source occurrence graph must be DAG')
    return groups


def synthesize_all_finite_tests(graph, circuits):
    quantitative = reason_over_quantified_evidence(graph)
    indexed = _index(graph, quantitative); groups = _groups(graph, circuits)
    rows, counts = [], Counter()
    for group in groups:
        complete_evidence = group['transition_evidence_complete'] and bool(group['evidence'])
        computation = synthesize_finite_set(graph, indexed, group['premises']) if complete_evidence else {
            'status': 'incomplete_transition_provenance', 'member_audit': [], 'summary': None}
        counts[computation['status']] += 1
        # Контроль получает тот же список знаний, но не стрелки, заключение или его содержание.
        flat = synthesize_finite_set(graph, indexed, sorted(group['premises']))
        identical = computation['summary'] == flat['summary']
        require(identical or not complete_evidence, 'Same-membership arithmetic depends on arrow metadata')
        rows.append({'group_id': group['id'], 'article_id': group['article_id'],
                     'head_reference_for_navigation_only': group['head'], 'members': deepcopy(group['premises']),
                     'arity': len(group['premises']), 'transition_evidence': deepcopy(group['evidence']),
                     **computation, 'same_members_without_arrows_identical': identical,
                     'head_content_used_as_operand': False, 'alternative_groups_merged': False})
    # Сильная база строит конечные списки из семантики самих измерений, не из авторских стрелок.
    buckets = defaultdict(list); rejected = []; scope_rejected = Counter()
    for pid, item in sorted(indexed.items()):
        if item['kind'] != 'measured_tests':
            rejected.append({'parent': pid, 'reason': item['kind']}); continue
        keys = {'source_family': set(), 'exact_analysis_scope': set()}
        for s, operation in zip(item['statements'], item['proof']['operations']):
            _, cutoff = parse_reported_operand(operation['operation']['reported_alpha'])
            base = (graph['parents'][pid]['article_id'], s['predicate'], _cohort(s), str(cutoff.normalize()))
            keys['source_family'].add(base)
            keys['exact_analysis_scope'].add((*base, _exact_analysis_scope(s)))
        if len(keys['source_family']) != 1:
            rejected.append({'parent': pid, 'reason': 'compound_parent_spans_multiple_semantic_set_keys'}); continue
        if len(keys['exact_analysis_scope']) != 1:
            scope_rejected['compound_parent_spans_multiple_analysis_scopes'] += 1
        for level, values in keys.items():
            if len(values) == 1:
                buckets[(level, next(iter(values)))].append(pid)
    semantic_sets_by_tests = {}
    candidate_sets_by_level = Counter()
    for (level, key), members in sorted(buckets.items()):
        computation = synthesize_finite_set(graph, indexed, members)
        candidate_sets_by_level[level] += 1
        row = {'grouping_level': level, 'grouping_key': list(key),
               'membership_origin': 'statement_semantics_without_author_groups', **computation}
        if row['summary'] is None:
            signature = fingerprint({'level': level, 'key': list(key), 'members': sorted(members)})
        else:
            signature = fingerprint({'cohort': row['summary']['cohort'], 'cutoff': row['summary']['cutoff'],
                'tests': sorted((t['parent'], t['statement_id']) for t in row['summary']['tests'])})
        previous = semantic_sets_by_tests.get(signature)
        if previous is None:
            row['grouping_levels'] = [level]; row['grouping_keys'] = [list(key)]
            semantic_sets_by_tests[signature] = row
        else:
            if level not in previous['grouping_levels']:
                previous['grouping_levels'].append(level)
            previous['grouping_keys'].append(list(key))
    semantic_sets = list(semantic_sets_by_tests.values())
    exact = sum(bool(r['summary']) and any(
        r['summary']['tests'] == b['summary']['tests'] for b in semantic_sets if b['summary']) for r in rows)
    return {'version': VERSION, 'question': None, 'model_calls': 0, 'target_read': False,
            'canonical_blocks': len(graph['parents']), 'native_statements': graph['statement_count'],
            'quantitative': quantitative, 'author_groups': rows, 'counts': dict(counts),
            'semantic_sets_without_author_groups': semantic_sets, 'baseline_parent_coverage': rejected,
            'baseline_grouping_diagnostics': {'candidate_sets_by_level': dict(candidate_sets_by_level),
                                               'parents_with_mixed_exact_scopes': scope_rejected['compound_parent_spans_multiple_analysis_scopes']},
            'same_members_without_arrows_identical': all(r['same_members_without_arrows_identical'] for r in rows),
            'exact_test_sets_also_found_without_groups': exact,
            'all_author_groups_accounted': len(rows) == len(groups), 'max_premise_members': None,
            'new_predictions': [], 'new_confirmed_predictions': 0, 'scientific_success': False,
            'graph_advantage_demonstrated': False,
            'policy_ru': 'Синтез использует весь явно перечисленный конечный список сообщённых тестов. '
                         'Составные блоки, модели, страты, числа и источники сохранены. Неизвестные части '
                         'не удаляются; независимость тестов не предполагается. Порог не заимствуется '
                         'из другого блока или статьи. Авторская группа задаёт список, но не доказывает '
                         'биологический закон. Контроль с тем же списком без стрелок отделён от базы, '
                         'которая сама формирует списки по семантике. Нового будущего исхода здесь нет.'}

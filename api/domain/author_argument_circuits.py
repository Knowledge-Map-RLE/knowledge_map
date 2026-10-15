"""Полные авторские И/ИЛИ-цепочки сохраняют вхождения и не становятся причинными законами."""
from collections import Counter, defaultdict, deque
from copy import deepcopy

from domain.article_maps import fingerprint, require
from domain.semantic_operator_graph import VERSION as GRAPH_VERSION
from domain.knowledge_development import ACTION_STATUSES

VERSION = 'source-bound-author-argument-circuits-2'
LIMITS = {'steps': 200000}


def classify_group(head, premises):
    if head['kind'] == 'action':
        return {'unresolved': 'task_proposal', 'planned': 'intention', 'prescribed': 'prescribed_procedure',
            'performed': 'performed_procedure'}[head['action_status']]
    if all(p['kind'] == 'action' and p['action_status'] == 'performed' for p in premises):
        return 'procedure_to_report'
    if all(p['kind'] == 'state' for p in premises): return 'content_to_state'
    return 'mixed_basis_to_state'


def build_circuits(graph, origins):
    require(graph['version'] == GRAPH_VERSION and graph['question'] is None and graph['model_calls'] == 0,
            'Complete source-only semantic graph required')
    parents, occurrences = graph['parents'], graph['visible_occurrences']
    require(origins is not None and set(origins['knowledge']) == {(p['article_id'], p['knowledge_id']) for p in parents.values()},
            'Exact source-origin coverage required for argument circuits')
    require({o['parent'] for o in occurrences.values()} == set(parents), 'Exact visible occurrence coverage required')
    for p in parents.values():
        native = p['complete_parent']
        require((native['kind'] == 'state' and native['action_status'] is None) or
            (native['kind'] == 'action' and native['action_status'] in ACTION_STATUSES), 'Invalid source action status')
        source = origins['sources'][p['article_id']]
        annotation = origins['knowledge'][p['article_id'], p['knowledge_id']]
        require(source['source_sha256'] == p['source_sha256'] and source['graph_sha256'] == p['graph_sha256']
            and annotation['knowledge_sha256'] == p['knowledge_sha256'], 'Argument origin binding differs')
    by_head, groups = defaultdict(list), {}
    for dependency in graph['author_dependencies']:
        head, body = dependency['conclusion'], dependency['premises']
        oh, ob = dependency['conclusion_occurrence'], dependency['premise_occurrences']
        require(head in parents and body and all(p in parents for p in body), 'Unknown argument parent')
        require(oh in occurrences and all(o in occurrences for o in ob) and len(ob) == len(body)
            and occurrences[oh]['parent'] == head
            and [occurrences[o]['parent'] for o in ob] == body, 'Argument occurrence identity differs')
        require(len(ob) == len(set(ob)) and oh not in ob, 'Repeated immediate argument occurrence')
        require(all(occurrences[o]['article_id'] == dependency['article_id'] == parents[head]['article_id'] for o in [oh, *ob]),
            'Cross-source author group')
        transition = dependency['original_transition']; source = origins['sources'][dependency['article_id']]
        evidence = [deepcopy(graph['source_units'][e]) for e in dependency['evidence']]
        require(all(e['article_id'] == dependency['article_id'] and e['source_sha256'] == source['source_sha256'] for e in evidence),
            'Transition evidence source differs')
        complete = {e['unit_id'] for e in evidence} == set(transition.get('unit_ids', [])) and bool(evidence)
        row = {'article_id': dependency['article_id'], 'head': head, 'premises': deepcopy(body),
            'head_occurrence': oh, 'premise_occurrences': deepcopy(ob),
            'classification': classify_group(parents[head]['complete_parent'], [parents[p]['complete_parent'] for p in body]),
            'original_transition': deepcopy(transition), 'evidence': evidence, 'transition_evidence_complete': complete,
            'source_sha256': source['source_sha256'], 'graph_sha256': source['graph_sha256'],
            'connective': 'all_members_required_by_this_author_group',
            'alternative_groups_are_jointly_required': False, 'deductive_rule': False, 'causal_rule': False}
        row['id'] = fingerprint(row)
        require(row['id'] not in groups, 'Repeated author transition')
        groups[row['id']] = row; by_head[oh].append(row['id'])
    # Топологическое раскрытие вхождений сохраняет весь DAG без декартова произведения путей.
    adjacency = defaultdict(set); indegree = {o: 0 for o in occurrences}
    expected = {(p, g['head_occurrence']) for g in groups.values() for p in g['premise_occurrences']}
    require(expected == {(e['source'], e['target']) for e in graph['visible_occurrence_edges']}, 'Argument groups and occurrence edges differ')
    for premise, head in expected:
        adjacency[premise].add(head); indegree[head] += 1
    queue = deque(sorted(o for o, n in indegree.items() if n == 0)); order = []
    while queue:
        oid = queue.popleft(); order.append(oid)
        for head in sorted(adjacency[oid]):
            indegree[head] -= 1
            if indegree[head] == 0: queue.append(head)
    require(len(order) == len(occurrences), 'Argument occurrence graph must be DAG')
    nodes = {}; steps = 0
    for oid in order:
        o = occurrences[oid]; p = parents[o['parent']]; native = p['complete_parent']
        branches = [{'group_id': gid, 'connective': 'and', 'members': groups[gid]['premise_occurrences']}
            for gid in sorted(by_head[oid])]
        depth = 1 + max(nodes[c]['depth'] for b in branches for c in b['members']) if branches else 0
        nodes[oid] = {'id': oid, 'parent': o['parent'], 'original_occurrence': deepcopy(o['original_occurrence']),
            'kind': native['kind'], 'action_status': native['action_status'], 'depth': depth,
            'branch_connective': 'or', 'branches': deepcopy(branches),
            'origin': deepcopy(origins['knowledge'][p['article_id'], p['knowledge_id']]),
            'complete_parent_sha256': p['knowledge_sha256'],
            'premise_truth_or_transport_established': False,
            'action_performed': native['kind'] == 'action' and native['action_status'] == 'performed',
            'nonperformed_action_is_observed_fact': False}
    roots, counts = [], Counter()
    for oid in sorted(nodes):
        node = nodes[oid]; record = parents[node['parent']]; seen, stack, used = set(), [oid], set()
        frontier = []
        while stack:
            current = stack.pop()
            if current in seen: continue
            steps += 1; require(steps <= LIMITS['steps'], 'Argument circuit budget exceeded; no partial publication')
            seen.add(current); n = nodes[current]
            if not n['branches']: frontier.append(current)
            for b in n['branches']: used.add(b['group_id']); stack.extend(b['members'])
        # Эти множества служат навигации. Они никогда не подменяют вложенные И/ИЛИ-группы.
        states = sorted({nodes[n]['parent'] for n in frontier if nodes[n]['kind'] == 'state'})
        actions = sorted({nodes[n]['parent'] for n in seen - {oid} if nodes[n]['kind'] == 'action'})
        primary = [p for p in states if any(s['origin'] == 'primary_result' for s in
            origins['knowledge'][parents[p]['article_id'], parents[p]['knowledge_id']]['statements'])]
        has_basis = bool(node['branches']) and bool(states)
        classification = 'has_content_basis_to_review' if has_basis else 'procedure_only_basis' if used and actions else 'no_expanded_content_basis'
        counts[classification] += 1
        roots.append({'article_id': record['article_id'], 'knowledge_id': record['knowledge_id'], 'parent': node['parent'], 'root': oid,
            'classification': classification, 'possible_state_leaves': states, 'possible_action_conditions': actions,
            'possible_primary_result_leaves': primary, 'union_of_leaves_is_not_a_joint_premise_group': True,
            'author_groups': sorted(used), 'depth': node['depth'], 'depth_truncated': False,
            'new_knowledge_or_rule_created': False})
    return {'version': VERSION, 'limits': deepcopy(LIMITS), 'question': None, 'model_calls': 0, 'target_read': False,
        'canonical_blocks': len(parents), 'visible_occurrences': len(occurrences), 'statement_count': graph['statement_count'],
        'roots': roots, 'nodes': nodes, 'groups': groups, 'counts': dict(counts),
        'group_classifications': dict(Counter(g['classification'] for g in groups.values())),
        'transition_forms': dict(Counter(parents[g['premises'][i]]['complete_parent']['kind'] + '_to_' +
            parents[g['head']]['complete_parent']['kind'] for g in groups.values() for i in range(len(g['premises'])))),
        'transition_evidence_incomplete': sum(not g['transition_evidence_complete'] for g in groups.values()),
        'steps': steps, 'maximum_depth': max((n['depth'] for n in nodes.values()), default=0),
        'new_predictions': [], 'scientific_success': False, 'graph_advantage_demonstrated': False,
        'policy_ru': 'Все вхождения и все уровни авторских цепочек сохранены. Совместные группы — И, альтернативные пути — ИЛИ. '
            'Это схема использования знания, не доказательство достаточности и не транзитивный причинный закон. '
            'Выполненные действия, намерения и задачи различаются. Полные родители, отрицания, контекст и происхождение сохранены. '
            'Наличие содержательного основания само по себе не лицензирует прогноз.'}

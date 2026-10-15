"""Полный граф скрытых ролей; сравнимое имя не означает тождество сущностей."""
from collections import Counter, defaultdict
from copy import deepcopy
from hashlib import sha256

from domain.article_maps import fingerprint, require
from domain.comparison_normalization import canonical, normalize_map, VERSION as NORMALIZER
from domain.whole_map_context import audit_index, apply_context_audit
from domain.development_prediction import validate_visible_dag

VERSION = 'whole-map-semantic-operator-graph-2'
LIMITS = {'pattern_steps': 200000, 'max_pattern_statements': 3}


def identifier(article, kind, local):
    return fingerprint({'article_id': article, 'node_kind': kind, 'local_id': local})


def cyclic_components(nodes, edges):
    """Итеративные компоненты сохраняют циклы скрытой семантики без раскрытия рекурсией."""
    adjacency = {n: [] for n in nodes}; reverse = {n: [] for n in nodes}
    for edge in edges:
        adjacency[edge['source']].append(edge['target']); reverse[edge['target']].append(edge['source'])
    seen = set(); order = []
    for start in sorted(nodes):
        if start in seen: continue
        stack = [(start, False)]
        while stack:
            node, leaving = stack.pop()
            if leaving: order.append(node); continue
            if node in seen: continue
            seen.add(node); stack.append((node, True))
            for other in reversed(adjacency[node]):
                if other not in seen: stack.append((other, False))
    seen.clear(); cycles = []
    for start in reversed(order):
        if start in seen: continue
        stack = [start]; component = []
        while stack:
            node = stack.pop()
            if node in seen: continue
            seen.add(node); component.append(node); stack.extend(reverse[node])
        if len(component) > 1 or start in adjacency[start]: cycles.append(sorted(component))
    return sorted(cycles, key=fingerprint)


def build_graph(maps, context_audit=None):
    require(bool(maps) and len({m['article_id'] for m in maps}) == len(maps), 'Explicit distinct maps required')
    audited = audit_index(maps, context_audit)
    nodes = {}; edges = []; parents = {}; statements = {}; units = {}; dependencies = []; coverage = []
    occurrences = {}; occurrence_edges = []
    for m in maps:
        article = m['article_id']; graph = m['graph']; source = m['source']
        require(graph['schema_version'] == 6, 'Semantic operator graph requires schema 6')
        validate_visible_dag(graph)
        graph_sha256 = fingerprint(graph)
        require(sha256(source['text'].encode()).hexdigest() == source['sha256'], 'Full source changed')
        require(source['offset_encoding'] == 'unicode_codepoints', 'Unicode source coordinates required')
        raw_units = {u['id']: u for u in source['units']}
        require(len(raw_units) == len(source['units']), 'Duplicate source unit')
        knowledge = {k['knowledge_id']: k for k in graph['knowledge']}
        require(len(knowledge) == len(graph['knowledge']), 'Duplicate canonical knowledge')
        visible = {n['id']: n['knowledge_id'] for n in graph['nodes']}
        require(len(visible) == len(graph['nodes']) and set(visible.values()) <= set(knowledge), 'Unknown visible knowledge')
        transition_edges = set()
        for transition in graph['transitions']:
            require(transition['target'] in visible and bool(transition['sources'])
                    and len(set(transition['sources'])) == len(transition['sources'])
                    and all(v in visible and v != transition['target'] for v in transition['sources']), 'Invalid source premise group')
            transition_edges.update((v, transition['target']) for v in transition['sources'])
        require(transition_edges == {(e['source'], e['target']) for e in graph['edges']}, 'Author groups and visible edges differ')
        concepts = {c['id']: c for c in graph['concepts']}
        require(len(concepts) == len(graph['concepts']), 'Duplicate native concept')
        for knowledge_item in knowledge.values():
            for statement in knowledge_item['semantic_frame']['statements']:
                for role in statement['roles']:
                    require(bool(role['concept_id']) != bool(role['knowledge_id']), 'Exactly one native role reference required')
                    require((role['concept_id'] in concepts) if role['concept_id'] else (role['knowledge_id'] in knowledge),
                            'Unknown semantic role reference')
        projected = {k['id']: apply_context_audit(k, knowledge[k['id']], audited.get((article, k['id']))) for k in normalize_map(m)}
        for cid, concept in concepts.items():
            nid = identifier(article, 'concept', cid)
            nodes[nid] = {'id': nid, 'kind': 'concept', 'article_id': article, 'native_id': cid,
                          'label': concept['display_text'], 'comparison_key': canonical(concept['display_text'], 'concepts'),
                          'cross_source_identity_established': False, 'source_sha256': source['sha256']}
        for kid, knowledge_item in knowledge.items():
            nid = identifier(article, 'knowledge', kid)
            nodes[nid] = {'id': nid, 'kind': 'knowledge', 'article_id': article, 'native_id': kid,
                          'label': knowledge_item['display_text'], 'knowledge_kind': knowledge_item['knowledge_kind'],
                          'state_or_action': knowledge_item['kind'], 'action_status': knowledge_item['action_status']}
            parents[nid] = {'article_id': article, 'run_id': m['run_id'], 'knowledge_id': kid,
                            'source_sha256': source['sha256'], 'graph_sha256': graph_sha256,
                            'knowledge_sha256': fingerprint(knowledge_item), 'complete_parent': deepcopy(knowledge_item)}
        for occurrence in graph['nodes']:
            oid = identifier(article, 'occurrence', occurrence['id'])
            occurrences[oid] = {'id': oid, 'article_id': article, 'native_id': occurrence['id'],
                'parent': identifier(article, 'knowledge', occurrence['knowledge_id']),
                'original_occurrence': deepcopy(occurrence)}
        require(set(visible.values()) == set(knowledge), 'Canonical knowledge missing a visible occurrence')
        occurrence_edges.extend({'source': identifier(article, 'occurrence', e['source']),
            'target': identifier(article, 'occurrence', e['target'])} for e in graph['edges'])
        for kid, knowledge_item in knowledge.items():
            parent = identifier(article, 'knowledge', kid); normalized = {s['id']: s for s in projected[kid]['statements']}
            require(len(normalized) == len(knowledge_item['semantic_frame']['statements']), 'Statement coverage changed')
            row_ids = []
            for position, original in enumerate(knowledge_item['semantic_frame']['statements']):
                sid = original['statement_id']; nid = identifier(article, 'statement', sid)
                require(nid not in nodes, 'Statement identity must be unique inside a source')
                norm = normalized[sid]; references = []
                evidence = []
                for uid in original['provenance']['unit_ids']:
                    require(uid in raw_units, 'Unknown statement source unit')
                    unit = raw_units[uid]; begin, end = unit['start'], unit['end']
                    require(type(begin) is int and type(end) is int and 0 <= begin < end <= source['content_end']
                            and source['text'][begin:end] == unit['text'], 'Statement source unit changed or bibliography used')
                    proof_id = identifier(article, 'source_unit', uid)
                    proof = {'id': proof_id, 'article_id': article, 'unit_id': uid, 'start': begin, 'end': end,
                             'text': unit['text'], 'sha256': sha256(unit['text'].encode()).hexdigest(), 'source_sha256': source['sha256']}
                    require(proof_id not in units or units[proof_id] == proof, 'Conflicting source proof')
                    units[proof_id] = proof; evidence.append(proof_id)
                require(bool(evidence), 'Grounded statement required')
                for index, role in enumerate(original['roles']):
                    require(bool(role['concept_id']) != bool(role['knowledge_id']), 'Exactly one native role reference required')
                    native = role['concept_id'] or role['knowledge_id']; kind = 'concept' if role['concept_id'] else 'knowledge'
                    require(native in (concepts if kind == 'concept' else knowledge), 'Unknown semantic role reference')
                    target = identifier(article, kind, native)
                    references.append({'role': canonical(role['role'], 'roles'), 'target': target, 'native_role': role['role'],
                                       'reference_kind': kind, 'position': index})
                    edges.append({'source': nid, 'target': target, 'kind': 'role', 'role': canonical(role['role'], 'roles'),
                                  'native_role': role['role'], 'position': index})
                nodes[nid] = {'id': nid, 'kind': 'statement', 'article_id': article, 'native_id': sid, 'parent': parent,
                              'predicate': norm['predicate'], 'native_predicate': original['predicate']}
                statement = {'id': nid, 'parent': parent, 'article_id': article, 'run_id': m['run_id'], 'statement_id': sid,
                    'position': position, 'predicate': norm['predicate'], 'roles': references, 'negated': norm['negated'],
                    'scope': deepcopy(norm['scope']), 'attributes': deepcopy(norm['attributes']),
                    'attribute_types': deepcopy(norm.get('attribute_types', {})),
                    'unknown_context': norm['unknown_context'], 'parent_logic': knowledge_item['semantic_frame']['logic'],
                    'state_or_action': knowledge_item['kind'], 'action_status': knowledge_item['action_status'],
                    'original_statement': deepcopy(original), 'evidence': evidence,
                    'independent_premise_licensed': False}
                # Наличие части в сети не лицензирует её как отдельную истинную посылку.
                statements[nid] = statement; row_ids.append(nid)
                edges.append({'source': parent, 'target': nid, 'kind': 'contains', 'position': position})
            coverage.append({'article_id': article, 'knowledge_id': kid, 'parent': parent, 'statements': row_ids,
                             'count': len(row_ids), 'full_parent_retained': True,
                             'reason_ru': 'Все части представлены в сети; независимые посылки требуют отдельной лицензии оператора.'})
        for transition in graph['transitions']:
            body = [identifier(article, 'knowledge', visible[v]) for v in transition['sources']]
            head = identifier(article, 'knowledge', visible[transition['target']])
            evidence = []
            # Обоснование стрелки может ссылаться на фрагмент, не использованный блоками.
            for uid in transition.get('unit_ids', []):
                require(uid in raw_units, 'Unknown transition source unit')
                unit = raw_units[uid]; begin, end = unit['start'], unit['end']
                require(type(begin) is int and type(end) is int and 0 <= begin < end <= source['content_end']
                    and source['text'][begin:end] == unit['text'], 'Transition source unit changed or bibliography used')
                proof_id = identifier(article, 'source_unit', uid)
                proof = {'id': proof_id, 'article_id': article, 'unit_id': uid, 'start': begin, 'end': end,
                    'text': unit['text'], 'sha256': sha256(unit['text'].encode()).hexdigest(), 'source_sha256': source['sha256']}
                require(proof_id not in units or units[proof_id] == proof, 'Conflicting transition source proof')
                units[proof_id] = proof; evidence.append(proof_id)
            dependencies.append({'article_id': article, 'premises': body, 'conclusion': head,
                'premise_occurrences': [identifier(article, 'occurrence', v) for v in transition['sources']],
                'conclusion_occurrence': identifier(article, 'occurrence', transition['target']),
                'evidence': evidence, 'original_transition': deepcopy(transition), 'deductive_rule': False})
    require(all(e['source'] in nodes and e['target'] in nodes for e in edges), 'Unknown semantic edge')
    require(len(statements) == sum(r['count'] for r in coverage), 'Whole-map statement coverage differs')
    cycles = cyclic_components(nodes, edges)
    return {'version': VERSION, 'normalizer_version': NORMALIZER, 'question': None, 'model_calls': 0,
            'canonical_blocks': len(parents), 'statement_count': len(statements), 'nodes': nodes, 'edges': edges,
            'parents': parents, 'statements': statements, 'source_units': units, 'coverage': coverage,
            'author_dependencies': dependencies, 'hidden_semantic_cycles': cycles,
            'visible_occurrences': occurrences, 'visible_occurrence_edges': occurrence_edges,
            'visible_dag_preserved': True, 'cross_source_entities_merged': 0,
            'scientific_success': False, 'graph_advantage_demonstrated': False}


def match_pattern(graph, pattern):
    """Сопоставление явных ролей ищет основания; само по себе ничего не выводит."""
    require(graph['version'] == VERSION and set(pattern) == {'statements', 'context_policy'}, 'Explicit semantic pattern required')
    slots = pattern['statements']
    require(1 <= len(slots) <= LIMITS['max_pattern_statements'] and pattern['context_policy'] == 'same_source_exact_scope',
            'Bounded source-local exact-context pattern required')
    for slot in slots:
        require(set(slot) == {'predicate', 'negated', 'state_or_action', 'action_status', 'roles'}, 'Exact pattern fields required')
        require(type(slot['negated']) is bool and slot['state_or_action'] in {'state', 'action'} and slot['roles'], 'Pattern status required')
        require(len({r['role'] for r in slot['roles']}) == len(slot['roles'])
                and all(set(r) == {'role', 'variable'} and r['role'] and r['variable'] for r in slot['roles']), 'Explicit unique variable roles required')
    candidates = []
    for slot in slots:
        candidates.append(sorted((s for s in graph['statements'].values() if not s['unknown_context']
            and s['predicate'] == slot['predicate'] and s['negated'] == slot['negated']
            and s['state_or_action'] == slot['state_or_action'] and s['action_status'] == slot['action_status']), key=lambda s: s['id']))
    results = []; steps = 0
    def walk(index, chosen, bindings):
        nonlocal steps
        if index == len(slots):
            results.append({'statements': [s['id'] for s in chosen], 'bindings': dict(bindings),
                'article_id': chosen[0]['article_id'], 'scope': deepcopy(chosen[0]['scope']),
                'parents': sorted({s['parent'] for s in chosen}), 'independent_premises_licensed': False,
                'interpretation_ru': 'Структурное соответствие; не логический вывод и не прогноз.'}); return
        for statement in candidates[index]:
            steps += 1; require(steps <= LIMITS['pattern_steps'], 'Semantic pattern budget exceeded; no partial publication')
            if statement['id'] in {s['id'] for s in chosen}: continue
            if chosen and (statement['article_id'] != chosen[0]['article_id'] or statement['scope'] != chosen[0]['scope']): continue
            role_index = defaultdict(list)
            for role in statement['roles']: role_index[role['role']].append(role['target'])
            result = dict(bindings); admitted = True
            for expected in slots[index]['roles']:
                actual = role_index[expected['role']]
                if len(actual) != 1: admitted = False; break
                value = actual[0]; variable = expected['variable']
                if variable in result and result[variable] != value: admitted = False; break
                result[variable] = value
            if admitted: walk(index + 1, chosen + [statement], result)
    walk(0, [], {})
    return {'version': VERSION, 'pattern_sha256': fingerprint(pattern), 'matches': results, 'steps': steps,
            'partial': False, 'predictions': [], 'scientific_success': False}


def inventory_patterns(graph, families):
    """Повторяемость структуры измеряется отдельно от истинности или применимости вывода."""
    require(graph['version'] == VERSION and set(families) == {v['article_id'] for v in graph['parents'].values()},
            'Explicit publication family registry required')
    participants = defaultdict(list)
    for s in graph['statements'].values():
        for role in s['roles']:
            participants[role['target']].append((s, role))
    patterns = {}; steps = 0
    for target, uses in sorted(participants.items()):
        for i, (left, left_role) in enumerate(uses):
            for right, right_role in uses[i + 1:]:
                steps += 1; require(steps <= LIMITS['pattern_steps'], 'Inventory budget exceeded; no partial result')
                if left['id'] == right['id']: continue
                slots = [{'predicate': s['predicate'], 'role': r['role'], 'negated': s['negated'],
                          'state_or_action': s['state_or_action'], 'action_status': s['action_status'],
                          'parent_logic': s['parent_logic']} for s, r in ((left, left_role), (right, right_role))]
                slots.sort(key=fingerprint)
                shape = {'statements': slots, 'shared_reference_kind': graph['nodes'][target]['kind']}
                key = fingerprint(shape)
                item = patterns.setdefault(key, {'id': key, 'shape': shape, 'examples': [], 'publications': set(),
                                                 'publication_families': set(), 'same_scope_examples': 0,
                                                 'unknown_context_examples': 0})
                item['publications'].add(left['article_id']); item['publication_families'].add(families[left['article_id']])
                same_scope = left['scope'] == right['scope']
                unknown = left['unknown_context'] or right['unknown_context']
                item['same_scope_examples'] += int(same_scope); item['unknown_context_examples'] += int(unknown)
                item['examples'].append({'statements': [left['id'], right['id']], 'shared_node': target,
                                         'article_id': left['article_id'], 'same_scope': same_scope,
                                         'unknown_context': unknown,
                                         'independent_premises_licensed': False})
    result = []
    for item in patterns.values():
        item['publications'] = sorted(item['publications']); item['publication_families'] = sorted(item['publication_families'])
        item['publication_support'] = len(item['publications'])
        item['status'] = 'structural_motif_only; no inference license'
        result.append(item)
    result.sort(key=lambda item: (-item['publication_support'], -len(item['examples']), item['id']))
    return {'version': VERSION, 'patterns': result, 'steps': steps,
            'patterns_in_multiple_publications': sum(p['publication_support'] >= 2 for p in result),
            'independent_primary_support_certified': False, 'predictions': [], 'scientific_success': False}

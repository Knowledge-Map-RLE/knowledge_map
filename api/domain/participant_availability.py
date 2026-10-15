"""Доступность символов вне заключения; наличие символа не доказывает новое утверждение."""
from collections import Counter, defaultdict

from domain.operator_pattern_forecast import validate_map_snapshot

VERSION = 'target-excluded-participant-availability-2'


def references(item):
    return {(('concept' if r.get('concept_id') else 'knowledge'), r.get('concept_id') or r.get('knowledge_id'))
            for s in item['semantic_frame']['statements'] for r in s['roles']}


def reachable(start, edges):
    """Замыкание работает и при циклах скрытых семантических ссылок."""
    visited, pending = set(), [start]
    while pending:
        item = pending.pop()
        for other in edges.get(item, ()):
            if other not in visited:
                visited.add(other)
                pending.append(other)
    return visited


def audit(snapshot):
    validate_map_snapshot(snapshot)
    graph = snapshot['graph']
    items = {k['knowledge_id']: k for k in graph['knowledge']}
    nodes = {n['id']: n['knowledge_id'] for n in graph['nodes']}
    providers, outgoing, incoming = defaultdict(set), defaultdict(set), defaultdict(set)
    symbols = {kid: references(item) for kid, item in items.items()}
    for kid, terms in symbols.items():
        for term in terms:
            providers[term].add(kid)
        # Само знание может выступать участником другого знания.
        providers[('knowledge', kid)].add(kid)
        for kind, reference in terms:
            if kind == 'knowledge':
                outgoing[reference].add(kid)
    for edge in graph['edges']:
        source, target = nodes[edge['source']], nodes[edge['target']]
        outgoing[source].add(target)
        incoming[target].add(source)
    counts, rows, seen = Counter(), [], set()
    for group in graph['transitions']:
        body, head = set(nodes[n] for n in group['sources']), nodes[group['target']]
        identity = (tuple(sorted(body)), head)
        if identity in seen:
            continue
        seen.add(identity)
        # Исключается не только заключение, но и все использующие его блоки.
        excluded = reachable(head, outgoing) | {head}
        ancestors = reachable(head, incoming) - excluded
        safe_body = body - excluded
        counts['groups_with_target_dependent_premises'] += bool(body & excluded)
        known = set().union(*(symbols[p] for p in safe_body)) | {('knowledge', p) for p in safe_body}
        missing = sorted(symbols[head] - known)
        if not missing:
            counts['no_new_symbol_in_head'] += 1
            continue
        decisions = []
        for term in missing:
            all_providers = providers[term]
            independent = all_providers - excluded
            upstream = independent & ancestors
            if upstream:
                status = 'other_ancestor_symbol'
            elif independent:
                status = 'off_chain_symbol'
            else:
                status = 'target_or_target_dependent_only'
            counts[status + '_terms'] += 1
            decisions.append({'reference_kind': term[0], 'reference': term[1], 'status': status,
                              'provider_count': len(independent), 'providers': sorted(independent),
                              'ancestor_providers': sorted(upstream),
                              'excluded_provider_count': len(all_providers & excluded)})
        complete = all(d['provider_count'] for d in decisions)
        counts['groups_all_new_symbols_elsewhere' if complete else 'groups_with_unavailable_symbols'] += 1
        rows.append({'article_id': snapshot['article_id'], 'run_id': snapshot['run_id'],
                     'premises': sorted(body), 'head': head, 'participants': decisions,
                     'excluded_target_dependent_premises': sorted(body & excluded),
                     'all_new_symbols_elsewhere': complete, 'excluded_head_dependent_count': len(excluded),
                     'source_sha256': snapshot['source']['sha256'],
                     'provenance': items[head]['provenance'], 'inference_licensed': False})
    return {'version': VERSION, 'article_id': snapshot['article_id'], 'counts': dict(counts), 'groups': rows,
            'policy_ru': 'Известность символа не означает известность отношения, совместимость контекста или допустимость вывода. '
                         'Заключение и зависимые от него по видимым и скрытым ссылкам знания исключены. '
                         'Порядок рангов не трактуется как календарная доступность.'}

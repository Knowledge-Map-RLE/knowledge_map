"""Контрольные режимы сохраняют семантику и меняют только источник групп."""
from collections import defaultdict
from itertools import combinations

from domain.article_maps import fingerprint

VERSION = 'whole-map-structure-controls-1'


def source_neighborhood_groups(records, width=3):
    """Окно по порядку карты внутри одного исходного фрагмента, без чтения DAG."""
    history, result, seen = defaultdict(list), [], set()
    for key, record in records.items():
        units = sorted({uid for p in record['provenance'] for uid in p['unit_ids']})
        for uid in units:
            local = history[(key[0], uid)]
            for size in range(1, min(width, len(local)) + 1):
                for body in combinations(local[-width:], size):
                    identity = (body, key)
                    if identity not in seen:
                        seen.add(identity)
                        result.append(identity)
            local.append(key)
    return result


def permuted_groups(records, groups):
    """Фиксированная перестановка подписей сохраняет топологию, размер и альтернативы."""
    by_source = defaultdict(list)
    for key in records:
        by_source[key[0]].append(key)
    mapping = {}
    for keys in by_source.values():
        ordered = sorted(keys)
        permuted = sorted(keys, key=lambda k: fingerprint({'version': VERSION, 'key': k}))
        # Для короткого совпавшего порядка фиксированная ротация гарантирует контроль.
        if ordered == permuted and len(keys) > 1:
            permuted = ordered[1:] + ordered[:1]
        mapping.update(zip(ordered, permuted))
    return [(tuple(mapping[p] for p in body), mapping[head]) for body, head in groups]


def known_baselines(records, families, limit):
    pool = {}
    for record in records.values():
        if not record['eligible']:
            continue
        identity = fingerprint(record['frame'])
        item = pool.setdefault(identity, {'id': identity, 'frame': record['frame'], 'support_families': set(),
            'premises': [], 'status': 'known_knowledge_baseline', 'novel_claim': False, 'logical_entailment': False,
            'causality_asserted': False})
        item['support_families'].add(families[record['key'][0]])
        item['premises'].append({'article_id': record['key'][0], 'knowledge_id': record['key'][1],
                                'run_id': record['run_id'], 'text': record['text'], 'provenance': record['provenance']})
    items = [{**p, 'support_families': sorted(p['support_families'])} for p in pool.values()]
    return {
        'known_union': sorted(items, key=lambda c: c['id'])[:limit],
        'frequency': sorted(items, key=lambda c: (-len(c['support_families']), c['id']))[:limit],
    }, {'eligible_known_pool': len(items), 'ranking': {'known_union': 'canonical_hash_order', 'frequency': 'distinct_provenance_families_then_hash'},
        'frequency_ties': 'deterministic; no preference learned from a target'}

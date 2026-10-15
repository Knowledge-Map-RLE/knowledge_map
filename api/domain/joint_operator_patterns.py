"""Поиск совместных мотивов переходов; мотив не является лицензией научного вывода."""
from collections import Counter
from copy import deepcopy
from itertools import permutations
import json

from domain.article_maps import fingerprint, require
from domain.comparison_normalization import canonical, normalize_attribute
from domain.operator_frame_routing import PREDICATES
from domain.operator_pattern_forecast import validate_map_snapshot

VERSION = "joint-author-motif-census-2"
MAX_PREMISES = 3


def signature(items, *, structural=False, internal_edges=()):
    """Канонизирует имена и порядок посылок, сохраняя совместное использование ролей."""
    require(2 <= len(items) <= MAX_PREMISES + 1, "One to three premises and a head required")
    require(len({k['knowledge_id'] for k in items}) == len(items), "Distinct canonical parents required")
    require(all(a != b and a in {k['knowledge_id'] for k in items[:-1]}
                and b in {k['knowledge_id'] for k in items[:-1]} for a, b in internal_edges),
            "Internal edges must connect distinct joint premises")
    variants = []
    for body in permutations(items[:-1]):
        ordered = [*body, items[-1]]
        slots = {k['knowledge_id']: index for index, k in enumerate(ordered)}
        variables = {}
        frames = []
        for item in ordered:
            frame = item['semantic_frame']
            statements = []
            for statement in frame['statements']:
                roles = []
                for role in sorted(statement['roles'], key=lambda r: r['role']):
                    kind = 'concept' if role.get('concept_id') else 'knowledge'
                    reference = role.get('concept_id') or role.get('knowledge_id')
                    if kind == 'knowledge' and reference in slots:
                        term = {'block_slot': slots[reference], 'reference_kind': kind}
                    else:
                        key = (kind, reference)
                        if key not in variables:
                            variables[key] = len(variables)
                        term = {'variable': variables[key], 'reference_kind': kind}
                    roles.append({'role': canonical(role['role'], 'roles'), 'term': term})
                predicate = canonical(statement['predicate'], 'predicates')
                if structural:
                    normal = ' '.join(predicate.casefold().replace('_', ' ').split())
                    predicate = PREDICATES.get(normal, 'unregistered:' + normal)
                row = {'predicate': predicate, 'roles': roles,
                       'negated': statement['negated'], 'quantifier': statement['quantifier'],
                       'modality': statement['modality']}
                if structural:
                    # Эти поля скрыты только при поиске формы, никогда при применении знания.
                    row['scope_presence'] = {'time': statement['temporal_context'] is not None,
                                             'conditions': bool(statement['conditions'])}
                    row['attribute_shapes'] = sorted(
                        [{'name': a['name'], 'unit': a.get('unit'), 'value_type': type(a['value']).__name__}
                         for a in map(normalize_attribute, statement['qualifiers']['attributes'])], key=fingerprint)
                else:
                    row.update({'time': deepcopy(statement['temporal_context']),
                                'conditions': sorted(deepcopy(statement['conditions']), key=fingerprint),
                                'attributes': sorted(map(normalize_attribute, statement['qualifiers']['attributes']), key=fingerprint)})
                statements.append(row)
            frames.append({'kind': item['kind'], 'action_status': item['action_status'],
                           'knowledge_kind': item['knowledge_kind'], 'logic': frame['logic'],
                           'statements': statements})
        variants.append({'arity': len(body), 'premises': frames[:-1], 'head': frames[-1],
                         'internal_edges': sorted((slots[a], slots[b]) for a, b in internal_edges),
                         'projection': 'structural_discovery_only' if structural else 'scope_and_values_retained'})
    # Порядок частей составного аргумента/контраста остаётся исходным.
    result = min(variants, key=lambda v: json.dumps(v, sort_keys=True, ensure_ascii=False))
    return {'id': fingerprint(result), **result}


def extract(snapshot):
    validate_map_snapshot(snapshot)
    graph = snapshot['graph']
    items = {k['knowledge_id']: k for k in graph['knowledge']}
    nodes = {n['id']: n['knowledge_id'] for n in graph['nodes']}
    edges = {(nodes[e['source']], nodes[e['target']]) for e in graph['edges']}
    counts, rows, seen = Counter(), [], set()
    for group in graph['transitions']:
        body, head = [nodes[n] for n in group['sources']], nodes[group['target']]
        counts['occurrence_groups'] += 1
        if len(set(body)) != len(body) or head in body:
            counts['repeated_canonical_parent'] += 1
            continue
        if len(body) > MAX_PREMISES:
            counts['over_three_joint_premises'] += 1
            continue
        identity = (tuple(sorted(body)), head)
        if identity in seen:
            counts['repeated_occurrence_group'] += 1
            continue
        seen.add(identity)
        counts[f'arity_{len(body)}'] += 1
        selected = [*(items[k] for k in body), items[head]]
        internal = [(a, b) for a, b in edges if a in body and b in body]
        counts['groups_with_internal_premise_edges'] += bool(internal)
        # Наличие нового участника в заключении — препятствие к его инстанцированию.
        def references(item):
            return {(('concept' if r.get('concept_id') else 'knowledge'),
                     r.get('concept_id') or r.get('knowledge_id'))
                    for s in item['semantic_frame']['statements'] for r in s['roles']}
        known_terms = set().union(*(references(item) for item in selected[:-1]))
        known_terms.update(('knowledge', key) for key in body)
        unbound = references(selected[-1]) - known_terms
        counts['groups_with_new_head_participants'] += bool(unbound)
        rows.append({'premises': body, 'head': head,
                     'texts': [k['display_text'] for k in selected],
                     'unit_ids': deepcopy(group.get('unit_ids', [])),
                     'new_head_participant_count': len(unbound),
                     'faithful': signature(selected, internal_edges=internal),
                     'structural': signature(selected, structural=True, internal_edges=internal)})
    return {'counts': dict(counts), 'groups': rows}


def census(snapshots, families):
    require(len({m['article_id'] for m in snapshots}) == len(snapshots) and bool(snapshots),
            "Unique explicit source maps required")
    require(set(families) == {m['article_id'] for m in snapshots}
            and all(isinstance(f, str) and f.strip() for f in families.values()), "Explicit source families required")
    grouped = {'faithful': {}, 'structural': {}}
    source_counts = []
    for snapshot in snapshots:
        article = snapshot['article_id']
        extracted = extract(snapshot)
        source_counts.append({'article_id': article, 'family': families[article],
                              'run_id': snapshot['run_id'], 'source_sha256': snapshot['source']['sha256'],
                              **extracted['counts']})
        for row in extracted['groups']:
            for mode in grouped:
                pattern = row[mode]
                record = grouped[mode].setdefault(pattern['id'], {'pattern': pattern, 'examples': []})
                record['examples'].append({'article_id': article, 'family': families[article],
                                           **{k: deepcopy(row[k]) for k in ('premises', 'head', 'texts', 'unit_ids', 'new_head_participant_count')}})
    modes = {}
    for mode, records in grouped.items():
        rows = []
        for record in records.values():
            sources = sorted({e['article_id'] for e in record['examples']})
            support = sorted({e['family'] for e in record['examples']})
            rows.append({**record, 'source_support': len(sources), 'family_support': len(support),
                         'sources': sources, 'families': support,
                         'inference_licensed': False, 'independence_certified': False})
        rows.sort(key=lambda r: (-r['family_support'], -r['source_support'], r['pattern']['id']))
        modes[mode] = {'pattern_count': len(rows), 'cross_source_patterns': sum(r['source_support'] >= 2 for r in rows),
                       'cross_family_patterns': sum(r['family_support'] >= 2 for r in rows), 'patterns': rows}
    return {'version': VERSION, 'maps': len(snapshots), 'max_joint_premises': MAX_PREMISES,
            'sources': source_counts, 'modes': modes, 'new_predictions': 0,
            'scientific_success': False, 'graph_advantage_demonstrated': False,
            'model_calls': 0, 'retrospective': True,
            'limitations_ru': ['Проверяется наличие повторяемой формы, а не истинность заключения.',
                               'Структурный режим скрывает конкретные условия, время и значения; применение такого мотива запрещено.',
                               'Семейства заданы входом; разные публикации не удостоверяют независимость данных.',
                               'Группы свыше трёх входов не разбиваются на удобные подмножества.',
                               'Все карты были известны до проверки; слепой прогноз не заявляется.']}

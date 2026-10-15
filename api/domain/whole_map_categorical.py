"""Логический канал всей карты: явная семантика классов, без домысливания кванторов."""
from collections import Counter, defaultdict
from itertools import combinations, permutations

from domain.article_maps import fingerprint, require
from domain.categorical_logic import check, VERSION as LOGIC_VERSION
from domain.whole_map_ablation import source_neighborhood_groups, permuted_groups

VERSION = 'whole-map-categorical-inference-2'
PREDICATES = {'class inclusion': ('A', 'all'), 'class disjointness': ('E', 'no'),
              'class overlap': ('I', 'some'), 'class noninclusion': ('O', 'some')}
LIMITS = {'max_premise_blocks': 3, 'max_categorical_premises': 3, 'max_terms': 3,
          'candidate_limit': 20, 'search_steps': 200000}


def project_record(record):
    frame = record['frame']
    if not record['eligible']: return None, 'unknown_parent_context'
    if frame['kind'] != 'state': return None, 'action_not_categorical_assertion'
    if frame['logic'] not in {'single', 'conjunction'}: return None, 'compound_logic_requires_explicit_license'
    parts = []
    for statement in frame['statements']:
        scope = statement['scope']
        if scope['quantifier'] is None: return None, 'explicit_quantifier_missing'
        if statement['predicate'] not in PREDICATES: return None, 'typed_class_relation_missing'
        form, quantifier = PREDICATES[statement['predicate']]
        if scope['quantifier'] != quantifier: return None, 'categorical_quantifier_mismatch'
        if statement['negated'] or scope['modality'] is not None: return None, 'negation_scope_or_modality_not_licensed'
        if statement['attributes']: return None, 'additional_constraints_require_explicit_license'
        roles = {r['role']: r['value'] for r in statement['roles']}
        if set(roles) != {'subject', 'class'} or len(roles) != len(statement['roles']):
            return None, 'categorical_roles_missing_or_repeated'
        if not all(isinstance(v, str) and v for v in roles.values()): return None, 'unresolved_categorical_class'
        context = {k: v for k, v in scope.items() if k != 'quantifier'}
        if context['study_group'] is None and not context['conditions'] and context['time'] is None:
            return None, 'categorical_scope_unknown'
        parts.append({'form': form, 'subject': roles['subject'], 'object': roles['class'], 'scope': context})
    if not 1 <= len(parts) <= LIMITS['max_categorical_premises']: return None, 'categorical_premise_budget'
    if any(p['scope'] != parts[0]['scope'] for p in parts): return None, 'mixed_categorical_scopes'
    return parts, None


def identity(proposition):
    # E и I симметричны; смена порядка классов не создаёт нового знания.
    value = dict(proposition)
    if value['form'] in {'E', 'I'}: value['subject'], value['object'] = sorted((value['subject'], value['object']))
    return fingerprint(value)


def apply(records, projected, bodies):
    known = {identity(p) for parts in projected.values() for p in parts}
    candidates = {}; rejected = Counter(); steps = 0; seen = set()
    for body in bodies:
        body = tuple(sorted(body))
        if body in seen: continue
        seen.add(body)
        if not 2 <= len(body) <= LIMITS['max_premise_blocks']: continue
        if any(key not in projected for key in body): continue
        parts = [p for key in body for p in projected[key]]
        if len(parts) > LIMITS['max_categorical_premises']:
            rejected['too_many_categorical_premises'] += 1; continue
        if any(p['scope'] != parts[0]['scope'] for p in parts):
            rejected['incompatible_scopes'] += 1; continue
        terms = sorted({p[k] for p in parts for k in ('subject', 'object')})
        if len(terms) > LIMITS['max_terms']:
            rejected['too_many_class_terms'] += 1; continue
        for subject, object_ in permutations(terms, 2):
            for form in ('A', 'E', 'I', 'O'):
                steps += 1
                require(steps <= LIMITS['search_steps'], 'Categorical search budget exceeded; no partial result')
                head = {'form': form, 'subject': subject, 'object': object_, 'scope': parts[0]['scope']}
                if identity(head) in known: continue
                proof = check(parts, head)
                if not proof['premises_consistent']:
                    rejected['inconsistent_premises'] += 1; continue
                if not proof['entailed']: continue
                # Каждая выбранная запись должна быть существенна; не добавляем декоративные посылки.
                redundant = False
                for key in body:
                    reduced = [p for other in body if other != key for p in projected[other]]
                    if check(reduced, head)['entailed']: redundant = True; break
                if redundant:
                    rejected['redundant_premise_block'] += 1; continue
                native = [{'article_id': key[0], 'knowledge_id': key[1], 'run_id': records[key]['run_id'],
                           'frame_sha256': fingerprint(records[key]['frame']), 'provenance': records[key]['provenance']}
                          for key in body]
                nodes = [{'id': 'premise:' + str(i), 'knowledge_id': p['knowledge_id']} for i, p in enumerate(native)]
                nodes += [{'id': 'operator', 'knowledge_id': LOGIC_VERSION},
                          {'id': 'conclusion', 'knowledge_id': 'derived:' + identity(head)}]
                candidate = {'id': identity(head), 'conclusion': head, 'premises': native,
                    'proof': proof, 'status': 'conditional_logical_consequence', 'novel_empirical_prediction': False,
                    'causality_asserted': False, 'expert_validated': False,
                    'proof_graph': {'nodes': nodes,
                        'edges': [{'source': n['id'], 'target': 'conclusion'} for n in nodes[:-1]],
                        'joint_premises': [n['id'] for n in nodes[:-1]], 'visible_dag': True}}
                prior = candidates.get(candidate['id'])
                if prior is None or fingerprint(native) < fingerprint(prior['premises']): candidates[candidate['id']] = candidate
    ranked = sorted(candidates.values(), key=lambda c: (len(c['premises']), c['id']))
    return ranked[:LIMITS['candidate_limit']], {'pool': len(ranked), 'search_steps': steps, 'rejected': dict(rejected)}


def infer(records, groups):
    require(all(head in records and all(p in records for p in body) and len(body) == len(set(body))
                and head not in body for body, head in groups), 'Unknown, repeated or self categorical dependency')
    projected = {}; coverage = []; counts = Counter(); by_source = defaultdict(list)
    for key, record in records.items():
        parts, reason = project_record(record)
        if parts is not None:
            projected[key] = parts; by_source[key[0]].append(key)
        else: counts[reason] += 1
        coverage.append({'article_id': key[0], 'knowledge_id': key[1],
                         'admitted': parts is not None, 'reason': reason, 'categorical_statements': parts or []})
    choices = {mode: [] for mode in ('graph', 'without_dependencies', 'source_neighborhood', 'permuted_dependencies')}
    choices['graph'] = [body for body, _ in groups]
    # Одно-входная зависимость связывает исходную посылку с зависимым определением.
    # Оба явно лицензированных категориальных фрагмента становятся посылками вывода.
    choices['graph'].extend(tuple(sorted((body[0], head))) for body, head in groups
                            if len(body) == 1 and body[0] != head)
    choices['source_neighborhood'] = [body for body, _ in source_neighborhood_groups(records)]
    choices['permuted_dependencies'] = [body for body, _ in permuted_groups(records, groups)]
    # Перебор только допущенных посылок; отсутствие квантора не заполняется автоматически.
    for keys in by_source.values():
        for count in (2, 3):
            choices['without_dependencies'].extend(combinations(keys, count))
            require(len(choices['without_dependencies']) <= LIMITS['search_steps'], 'Categorical pairing budget exceeded')
    modes = {}; diagnostic = {}
    for mode, bodies in choices.items(): modes[mode], diagnostic[mode] = apply(records, projected, bodies)
    return {'version': VERSION, 'logic_version': LOGIC_VERSION, 'limits': LIMITS, 'coverage': coverage,
        'admitted_blocks': len(projected), 'admitted_statements': sum(map(len, projected.values())),
        'rejected': dict(counts), 'consequences': modes, 'diagnostics': diagnostic,
        'new_empirical_predictions': 0, 'graph_advantage_demonstrated': False, 'model_calls': 0,
        'policy': 'Logical consequences remain conditional on source premises; they are not new observations or validated scientific forecasts.'}

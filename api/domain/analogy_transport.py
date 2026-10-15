"""Аналогия сохраняет полные посылки; различия контекста создают задачи проверки переноса."""
from collections import Counter, defaultdict
from copy import deepcopy
from itertools import permutations

from domain.article_maps import fingerprint, require
from domain.whole_map_forecast import project
from domain.whole_map_provenance import partition_provenance
from domain.semantic_part_projection import project_parts
from domain.evidence_origin_audit import validate_origins

VERSION = 'whole-map-analogy-transport-1'
LIMITS = {'search_steps': 200000, 'candidate_limit': 20}
# Общая категория не подменяет исходный предикат: сопоставление требует точного имени.
PREDICATES = {
    'associated with', 'risk factor association', 'reported lower cognition association',
    'reported faster decline association', 'reported slower decline association',
    'expression increased', 'reduced after intervention', 'exacerbated after intervention',
    'improved after intervention', 'memory performance improved',
    'plaque burden reduced after intervention', 'plaque count reduced after intervention',
    'concentration reduced after intervention', 'cell count reduced after intervention',
    'morphology preserved after intervention', 'downregulation prevented',
    'apical localization preserved', 'induction attenuated', 'induction abrogated', 'induction prevented',
}
CHANGED_ROLES = {'intervention', 'exposure', 'factor'}
CONTEXT_ROLES = {'population', 'cohort', 'tissue', 'model', 'challenge', 'phase', 'species', 'genotype'}
POLICY_RU = (
    'P(a,x), P(b,x), Q(a,y) предлагают проверить Q(b,y), но не влекут его. '
    'Все три посылки — собственные результаты первичных исследований с логически лицензированной частью. '
    'Числа и статистическая значимость не переносятся. Точное совпадение контекста даёт исследовательскую '
    'гипотезу; любое различие требует отдельной проверки переноса и не засчитывается прогнозом. '
    'Роль популяции заменяется только по наблюдаемой второй посылке вместе с вмешательством, '
    'без отождествления двух популяций. Поддержка посылок не является подтверждением заключения.'
)
TESTED_PREDICATES = {
    'memory performance improved': {'memory performance improved', 'memory performance difference',
                                    'improvement not statistically detected'},
    'induction attenuated': {'induction attenuated', 'induction abrogated', 'induction prevented',
                            'inflammatory response change not detected'},
}


def roles(statement):
    result = {r['role']: r['value'] for r in statement['roles']}
    return result if len(result) == len(statement['roles']) else None


def admissible(view):
    frame = view['frame']; statement = frame['statements'][0]; r = roles(statement)
    if not view['eligible']: return 'unknown_parent_context'
    if frame['kind'] != 'state' or frame['action_status'] is not None: return 'not_observed_state'
    if statement['negated'] or statement['scope'].get('modality') is not None: return 'negative_or_modal_premise'
    if statement['predicate'] not in PREDICATES: return 'no_qualitative_analogy_operator'
    if r is None or not r or any(not isinstance(v, str) for v in r.values()): return 'unresolved_or_duplicate_role'
    proof = view['projection_proof']
    if proof['origin']['origin'] != 'primary_result': return 'not_own_primary_result'
    if view.get('document_kind') != 'primary_study': return 'not_primary_document'
    # Качественное наблюдение не выдумывается из коэффициента или неопределённого результата теста.
    return None


def scope_differences(left, right):
    require(set(left) == set(right), 'Analogy scope fields differ')
    return {key: {'donor': deepcopy(left[key]), 'receiver': deepcopy(right[key])}
            for key in sorted(left) if left[key] != right[key]}


def same_measured_roles(left, right):
    a, b = roles(left), roles(right)
    if a is None or b is None: return False
    # Недостающая контекстная роль не доказывает различие экспериментов; конфликт значений сохраняется.
    common = set(a) & set(b)
    return bool(common) and not ((set(a) ^ set(b)) - CONTEXT_ROLES) and all(a[r] == b[r] for r in common)


def propose(views, all_known, groups, families):
    eligible = []; counts = Counter(); by_predicate = defaultdict(list)
    for v in sorted(views.values(), key=lambda row: row['key']):
        reason = admissible(v)
        counts[reason or 'admitted_qualitative_view'] += 1
        if reason is None:
            eligible.append(v); by_predicate[v['frame']['statements'][0]['predicate']].append(v)
    edges = {(p, h) for body, h in groups for p in body}
    known = defaultdict(list)
    for v in all_known: known[v['predicate']].append(v)
    pool = {}; steps = 0; tested_gaps = {}
    for anchors in by_predicate.values():
        for first, second in permutations(anchors, 2):
            a, b = first['frame']['statements'][0], second['frame']['statements'][0]
            ra, rb = roles(a), roles(b)
            common = set(ra) & set(rb)
            unmatched = set(ra) ^ set(rb)
            if unmatched - CONTEXT_ROLES:
                counts['noncontext_role_signature_mismatch'] += 1; continue
            changed = {role: (ra[role], rb[role]) for role in common if ra[role] != rb[role]}
            intervention_roles = set(changed) & CHANGED_ROLES
            if len(intervention_roles) != 1 or set(changed) - CHANGED_ROLES - CONTEXT_ROLES: continue
            if not common - set(changed): continue
            if len({v[0] for v in changed.values()}) != len(changed): continue
            if len({v[1] for v in changed.values()}) != len(changed): continue
            substitutions = dict(changed.values())
            for donor in eligible:
                steps += 1
                require(steps <= LIMITS['search_steps'], 'Analogy budget exceeded; no partial result')
                if donor['native_key'][0] != first['native_key'][0]: continue
                if donor['key'] in {first['key'], second['key']}: continue
                q = donor['frame']['statements'][0]; rq = roles(q)
                if q['predicate'] == a['predicate'] and rq == ra: continue
                changed_role = next(iter(intervention_roles))
                if rq.get(changed_role) != ra[changed_role]: continue
                # Каждая изменяемая ось должна присутствовать в донорском знании с тем же смыслом роли.
                if any(rq.get(role) != old for role, (old, _) in changed.items()): continue
                if any(value in substitutions and role not in changed for role, value in rq.items()): continue
                proposed = deepcopy(donor['frame']); head = proposed['statements'][0]
                for r in head['roles']:
                    if r['role'] in changed: r['value'] = changed[r['role']][1]
                if len(set(roles(head).values())) < len(set(rq.values())):
                    counts['participant_collapse_blocked'] += 1; continue
                # Для чисел, p, величины эффекта и статистического статуса сохраняется только исходное доказательство.
                head['attributes'] = []; head.pop('attribute_types', None)
                diffs = scope_differences(a['scope'], b['scope'])
                donor_diffs = scope_differences(a['scope'], q['scope'])
                context_roles = {r: {'donor': old, 'receiver': new} for r, (old, new) in changed.items() if r in CONTEXT_ROLES}
                unmatched_context = {role: {'donor': deepcopy(ra.get(role)), 'receiver': deepcopy(rb.get(role))}
                                     for role in sorted(unmatched)}
                obligations = {'anchor_scopes': diffs, 'donor_scopes': donor_diffs, 'context_roles': context_roles,
                    'unmatched_context_roles': unmatched_context,
                    'donor_attributes_not_licensed_for_transfer': deepcopy(q['attributes']),
                    'same_qualitative_response_under_substituted_factor_not_established': True}
                strict = not (diffs or donor_diffs or context_roles or unmatched_context or q['attributes'])
                # При различии контекста готового утверждения нет: хранится только задача переноса.
                # Неизвестность в неподелённых аргументах также не превращается в новизну.
                represented = [s for s in known[q['predicate']] if roles(s) == roles(head) and s['negated'] == head['negated']]
                if represented:
                    counts['known_relation_gap_blocked'] += 1; continue
                opposite = [s for s in known[q['predicate']] if roles(s) == roles(head) and s['negated'] != head['negated']]
                if opposite:
                    counts['opposite_relation_requires_review'] += 1; continue
                tested = [s for p in TESTED_PREDICATES.get(q['predicate'], {q['predicate']})
                          for s in known[p] if same_measured_roles(head, s)]
                if tested:
                    counts['already_tested_outcome_not_a_gap'] += 1
                    ident = fingerprint({'draft': proposed, 'known_tests': tested})
                    tested_gaps[ident] = {'id': ident, 'draft': proposed, 'already_recorded_tests': deepcopy(tested),
                        'reason_ru': 'Исход уже исследован; недостоверный результат теста не означает отсутствия эффекта.',
                        'explicit_logical_contradiction': False, 'included_in_new_hypotheses': False}
                    continue
                identity = fingerprint({'frame': proposed, 'obligations': obligations})
                native = [v['native_key'] for v in (first, second, donor)]
                author_edges = [[list(p), list(h)] for p, h in sorted(edges)
                                if p in native and h in native]
                witness = {'premises': [{'part_key': list(v['key']), 'native_key': list(v['native_key']),
                    'run_id': v['run_id'], 'text': v['text'], 'complete_projection_proof': deepcopy(v['projection_proof'])}
                    for v in (first, second, donor)], 'substitutions': {r: {'from': old, 'to': new} for r, (old, new) in sorted(changed.items())},
                    'author_internal_edges': author_edges, 'author_asserted_this_rule': False,
                    'premise_publication_families': sorted({families[k[0]] for k in native})}
                c = pool.setdefault(identity, {'id': identity, 'operator': VERSION,
                    'status': 'exploratory_scope_matched_hypothesis' if strict else 'unvalidated_transport_task',
                    'generated_knowledge_kind': 'hypothesis' if strict else 'research_task',
                    'generated_action_status': None if strict else 'unresolved',
                    'proposed_qualitative_frame': proposed, 'transport_obligations': obligations,
                    'proposed_scope_status': 'scope_matched' if strict else 'donor_scope_retained_not_receiver_validated',
                    'witnesses': [], 'logical_entailment': False, 'quantitative_prediction': None,
                    'statistical_significance_prediction': None, 'causal_transport_established': False,
                    'conclusion_support_families': [], 'expert_validated': False})
                if fingerprint(witness) not in {fingerprint(w) for w in c['witnesses']}: c['witnesses'].append(witness)
    ordered = sorted(pool.values(), key=lambda c: (
        len(c['transport_obligations']['anchor_scopes']) + len(c['transport_obligations']['donor_scopes']) + len(c['transport_obligations']['context_roles']) + len(c['transport_obligations']['unmatched_context_roles']) + bool(c['transport_obligations']['donor_attributes_not_licensed_for_transfer']),
        -len({f for w in c['witnesses'] for f in w['premise_publication_families']}), c['id']))
    hypotheses = [c for c in ordered if c['status'] == 'exploratory_scope_matched_hypothesis']
    tasks = [c for c in ordered if c['status'] == 'unvalidated_transport_task']
    return {'hypotheses': hypotheses[:LIMITS['candidate_limit']], 'transport_tasks': tasks[:LIMITS['candidate_limit']],
        'all_proposals': ordered, 'pool_counts': {'scope_matched': len(hypotheses), 'transport_required': len(tasks)},
        'already_tested_gaps': list(tested_gaps.values()), 'search_steps': steps, 'view_decisions': dict(counts)}


def discover_analogies(maps, families, context_audit, origin_audit):
    require(set(families) == {m['article_id'] for m in maps}, 'Explicit analogy families required')
    origins = validate_origins(maps, origin_audit)
    originals, groups, _ = project(maps, context_audit)
    for m in maps:
        for k in m['graph']['knowledge']:
            originals[m['article_id'], k['knowledge_id']]['native_knowledge'] = deepcopy(k)
    records, partition = partition_provenance(originals, families)
    views, _, _, coverage = project_parts(records, originals, origins)
    for v in views.values(): v['document_kind'] = origins['sources'][v['key'][0]]['document_kind']
    # Полный корпус, включая неподелённые сравнения, закрывает уже описанные отношения.
    all_known = [{**deepcopy(s), 'source_key': list(key), 'statement_position': position}
                 for key, r in records.items() for position, s in enumerate(r['frame']['statements'])]
    result = propose(views, all_known, groups, families)
    flat = propose(views, all_known, [], families)
    require([c['id'] for c in result['all_proposals']] == [c['id'] for c in flat['all_proposals']],
            'Analogy ablation unexpectedly changed semantic proposals')
    return {'version': VERSION, 'question': None, 'limits': LIMITS, 'policy_ru': POLICY_RU,
        'canonical_blocks': len(originals), 'native_statements': len(all_known), 'licensed_views': len(views),
        'coverage': coverage, 'provenance_partition': partition, **result,
        'ablation': {'visible_dependencies': result['pool_counts'], 'without_visible_dependencies': flat['pool_counts'],
            'same_proposal_ids': True, 'hidden_roles_retained_in_both_modes': True,
            'reason_ru': 'Оператор использует скрытые роли; авторские стрелки сохраняются в свидетельстве, '
                         'но сами по себе не разрешают перенос воздействия.'},
        'model_calls': 0, 'target_read': False, 'future_results_scored': 0, 'accuracy': None,
        'scientific_success': False, 'graph_advantage_demonstrated': False}

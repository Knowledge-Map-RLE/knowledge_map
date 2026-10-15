"""Аналогия над лицензированными частями сохраняет условия, родителей и неопределённость."""
from collections import Counter, defaultdict
from copy import deepcopy
from hashlib import sha256
from decimal import Decimal, InvalidOperation

from domain.article_maps import fingerprint, require
from domain.analogy_transport import PREDICATES, CHANGED_ROLES, CONTEXT_ROLES, TESTED_PREDICATES, roles
from domain.semantic_operator_graph import VERSION as GRAPH_VERSION, identifier
from domain.semantic_part_forecast import VERSION as PART_VERSION
from domain.semantic_part_projection import VERSION as PROJECTION_VERSION
from domain.qualitative_result_projection import summary_kind
from domain.forecast_attribute_kinds import blocks_unmodelled_numeric_transfer
from domain.evidence_origin_audit import VERSION as ORIGIN_VERSION

VERSION = 'whole-map-licensed-part-analogy-1'
LIMITS = {'search_steps': 200000, 'candidate_limit': 20}
POLICY_RU = (
    'P(a,x), P(b,x), Q(a,y) предлагают гипотезу Q(b,y), но не влекут её. '
    'Поиск охватывает все лицензированные части явно выбранного корпуса. '
    'Условия и атрибуты не удаляются; родительские противопоставления сохраняются. '
    'Качественные величины уже отделены от числовых сводок источниковым оператором. '
    'Различия времени, дозы, популяции, метода и происхождения остаются обязательствами проверки. '
    'Общий текст названия между статьями не удостоверяет тождество сущностей. '
    'Аналогия задана явно, а не выучена как закон из независимых повторений.'
)
# Поля описывают опубликованные сводки Y-maze, а не дозу или будущий ответ.
MEMORY_PERCENT_FIELDS = frozenset({'app percent', 'ko app percent', 'ko a beta percent', 'normal percent',
    'wt a beta percent', 'tros a beta percent', 'vehicle a beta percent'})
MEMORY_P_FIELDS = frozenset({'ko vs wt p', 'normal vs wt p', 'normal vs vehicle p', 'tros vs vehicle p'})
PROTOCOL_NUMERIC_FIELDS = {'injected concentration ug per ml': 'ug/ml', 'injected volume ul': 'ul',
    'sbfsem scale um': 'um', 'tem inset scale um': 'um', 'tem scale um': 'um', 'staining scale um': 'um'}
SOURCE_QUALIFICATION_FIELDS = frozenset({'source qualification', 'caption panel status'})


def _decimal(value):
    if not isinstance(value, str): return None
    try: result = Decimal(value)
    except InvalidOperation: return None
    return result if result.is_finite() else None


def _summary_extension(attribute, predicate):
    if predicate != 'memory performance improved': return None
    point = _decimal(attribute['value'])
    if point is None: return None
    if attribute['name'] in MEMORY_PERCENT_FIELDS and attribute['unit'] == 'percent' and 0 <= point <= 100:
        return 'reported_memory_readout'
    if attribute['name'] in MEMORY_P_FIELDS and attribute['unit'] == 'dimensionless' and 0 <= point <= 1:
        return 'reported_memory_test_summary'
    return None


def _direction_view(view):
    target = deepcopy(view); s = target['frame']['statements'][0]
    # Дополнительное выделение разрешено только для уже источниково проверенного качественного результата.
    if not view['projection_proof']['qualitative_result_proof_id']: return target
    removed = [{'position': i, 'attribute': deepcopy(a), 'kind': kind}
               for i, a in enumerate(s['attributes']) if (kind := _summary_extension(a, s['predicate']))]
    if not removed: return target
    positions = {r['position'] for r in removed}
    s['attributes'] = [a for i, a in enumerate(s['attributes']) if i not in positions]
    proof = {'version': VERSION + '+memory-direction-1', 'source_part_proof_id': view['projection_proof']['id'],
        'input_frame': deepcopy(view['frame']), 'output_frame': deepcopy(target['frame']), 'removed_summaries': removed,
        'conditions_removed': False, 'participants_changed': False, 'direction_inferred_from_numbers': False,
        'statistical_significance_transferred': False, 'new_measurement': False}
    proof['id'] = fingerprint(proof); target['direction_operand_proof'] = proof
    return target


def _is_protocol_or_qualification(attribute):
    if attribute['name'] in SOURCE_QUALIFICATION_FIELDS and attribute['unit'] is None and isinstance(attribute['value'], str):
        return True
    point = _decimal(attribute['value'])
    return (attribute['name'] in PROTOCOL_NUMERIC_FIELDS and attribute['unit'] == PROTOCOL_NUMERIC_FIELDS[attribute['name']]
            and point is not None and point > 0)


def _validate_inputs(parts, graph, origins):
    require(parts['version'] in {PART_VERSION, PART_VERSION + '+contrast-clause-license-1'},
            'Compatible sealed semantic-parts version required')
    require(graph['version'] == GRAPH_VERSION and parts['question'] is None and graph['question'] is None
            and parts['model_calls'] == graph['model_calls'] == 0 and parts['target_read'] is False,
            'Complete question-free source-only semantic snapshots required')
    parents = graph['parents']; statements = graph['statements']; units = graph['source_units']
    require(len(parents) == parts['canonical_blocks'] == graph['canonical_blocks']
            and len(statements) == graph['statement_count'], 'Incomplete canonical graph coverage')
    origin_sources = {s['article_id']: s for s in origins['sources']}
    require(len(origin_sources) == len(origins['sources']) and origins['model_calls'] == 0
            and origins['version'] == ORIGIN_VERSION and origins['author'] == 'Codex'
            and origins['expert_validated'] is False,
            'Exact explicit origin sources required')
    parent_keys = {(p['article_id'], p['knowledge_id']): p for p in parents.values()}
    require(len(parent_keys) == len(parents) and set(origin_sources) == {k[0] for k in parent_keys},
            'Origin corpus and semantic corpus differ')
    annotations = {}
    for article, source in origin_sources.items():
        for row in source['knowledge']:
            key = (article, row['knowledge_id'])
            require(key not in annotations and key in parent_keys, 'Unknown or duplicate origin parent')
            parent = parent_keys[key]
            require(source['run_id'] == parent['run_id'] and source['source_sha256'] == parent['source_sha256']
                    and source['graph_sha256'] == parent['graph_sha256']
                    and row['knowledge_sha256'] == parent['knowledge_sha256'], 'Native origin binding differs')
            annotations[key] = row['statements']
    require(set(annotations) == set(parent_keys), 'Complete canonical origin annotation required')
    coverage = parts['coverage']['coverage']
    require(len(coverage) == len(parents) and {(r['article_id'], r['knowledge_id']) for r in coverage} == set(parent_keys),
            'Incomplete semantic-part coverage')
    view_keys = set(); views_by_parent = defaultdict(list)
    for view in parts['part_views']:
        key = tuple(view['key']); native = tuple(view['native_key']); proof = view['projection_proof']
        require(key not in view_keys and native in parent_keys, 'Unknown or duplicate licensed part')
        view_keys.add(key); views_by_parent[native].append(key)
        parent = parent_keys[native]; position = view['statement_position']
        require(type(position) is int and 0 <= position < len(annotations[native]), 'Unknown source statement position')
        require(proof['version'] == PROJECTION_VERSION and proof['id'] == fingerprint({k: v for k, v in proof.items() if k != 'id'})
                and proof['view_frame_sha256'] == fingerprint(view['frame']), 'Projection proof or view changed')
        require(proof['parent_knowledge_sha256'] == parent['knowledge_sha256']
                and fingerprint(proof['complete_native_knowledge']) == parent['knowledge_sha256']
                and proof['complete_native_knowledge'] == parent['complete_parent']
                and proof['parent_key'] == list(native) and view['run_id'] == parent['run_id']
                and proof['run_id'] == parent['run_id'] and proof['statement_position'] == position
                and proof['origin'] == annotations[native][position], 'Part provenance or source origin changed')
        require(proof['parent_frame_sha256'] == fingerprint(proof['complete_parent_frame'])
                and view['frame']['logic'] == 'single' and len(view['frame']['statements']) == 1,
                'Complete licensed parent and single comparison part required')
        sid = identifier(native[0], 'statement', proof['native_statement_id'])
        require(sid in statements and statements[sid]['position'] == position
                and statements[sid]['parent'] == identifier(native[0], 'knowledge', native[1]), 'Native statement identity differs')
        evidence = [units[u] for u in statements[sid]['evidence']]
        require({u['unit_id'] for u in evidence} == set(proof['origin']['evidence_unit_ids']), 'Part evidence differs')
        for unit in evidence:
            require(unit['article_id'] == native[0] and unit['source_sha256'] == parent['source_sha256']
                    and len(unit['text']) == unit['end'] - unit['start']
                    and sha256(unit['text'].encode()).hexdigest() == unit['sha256'], 'Unicode source proof changed')
    require(len(view_keys) == parts['licensed_parts'], 'Licensed part total differs')
    for row in coverage:
        require({tuple(k) for k in row['licensed_views']} == set(views_by_parent[row['article_id'], row['knowledge_id']]),
                'Part coverage changed')
    return parent_keys, origin_sources


def _native_roles(view, graph):
    proof = view['projection_proof']; article = view['native_key'][0]
    statement = graph['statements'][identifier(article, 'statement', proof['native_statement_id'])]
    mapped = {r['role']: r for r in statement['roles']}
    return mapped if len(mapped) == len(statement['roles']) else None


def _admission(view, graph, sources):
    frame = view['frame']; s = frame['statements'][0]; r = roles(s)
    if not view['eligible']: return 'unknown_parent_context'
    if frame['kind'] != 'state' or frame['action_status'] is not None: return 'not_observed_state'
    if s['negated'] or s['scope'].get('modality') is not None: return 'negative_or_modal_premise'
    if s['predicate'] not in PREDICATES: return 'no_registered_qualitative_analogy'
    if view['projection_proof']['origin']['origin'] != 'primary_result': return 'not_own_primary_result'
    if sources[view['native_key'][0]]['document_kind'] != 'primary_study': return 'not_primary_document'
    raw = _native_roles(view, graph)
    if r is None or raw is None or set(r) != set(raw): return 'ambiguous_role_signature'
    if any(v['reference_kind'] != 'concept' for v in raw.values()): return 'nested_knowledge_requires_separate_operator'
    if not any(role in r for role in CHANGED_ROLES): return 'no_substitutable_factor_role'
    if s.get('attribute_types'): return 'typed_attribute_requires_separate_operator'
    if any(a['name'] in MEMORY_PERCENT_FIELDS | MEMORY_P_FIELDS for a in s['attributes']):
        return 'unprojected_or_invalid_memory_summary'
    if any(a['name'] in PROTOCOL_NUMERIC_FIELDS and not _is_protocol_or_qualification(a) for a in s['attributes']):
        return 'invalid_protocol_quantity'
    if any(summary_kind(a, s['predicate']) is not None for a in s['attributes']):
        return 'unprojected_numerical_or_statistical_summary'
    if any(blocks_unmodelled_numeric_transfer(a) and not _is_protocol_or_qualification(a) for a in s['attributes']):
        return 'unmodelled_numeric_attribute'
    return None


def _scope_diff(a, b):
    require(set(a) == set(b), 'Incompatible explicit scope fields')
    return {k: {'donor': deepcopy(a[k]), 'recipient': deepcopy(b[k])} for k in sorted(a) if a[k] != b[k]}


def _attrs_diff(a, b):
    return [] if a == b else [{'donor': deepcopy(a), 'recipient': deepcopy(b)}]


def _known_statements(graph):
    result = []
    for native in graph['statements'].values():
        r = {}
        for role in native['roles']:
            node = graph['nodes'][role['target']]
            value = node['comparison_key'] if node['kind'] == 'concept' else 'knowledge:' + role['target']
            require(role['role'] not in r, 'Duplicate native role in known-statement registry')
            r[role['role']] = value
        result.append({'predicate': native['predicate'], 'roles': r, 'negated': native['negated'],
                       'source_statement': native['id'], 'scope': deepcopy(native['scope'])})
    return result


def _newness(head, known):
    r = roles(head)
    tested = TESTED_PREDICATES.get(head['predicate'], {head['predicate']})
    for s in known:
        if s['predicate'] not in tested: continue
        common = set(s['roles']) & set(r)
        if ((set(s['roles']) ^ set(r)) - CONTEXT_ROLES or not common
                or any(s['roles'][role] != r[role] for role in common)): continue
        if s['predicate'] == head['predicate']:
            return ('known_relation' if s['negated'] == head['negated'] else 'explicit_opposite'), s
        return 'already_tested_endpoint', s
    return None, None


def _obligation_cost(obligations):
    return sum(bool(v) for k, v in obligations.items()
               if k not in {'causal_response_transport_established', 'cross_source_entity_identity_established'}) \
        + (not obligations['cross_source_entity_identity_established'])


def _search(views, graph, sources, families, known):
    candidates = {}; rejected = Counter(); blocked = {}; steps = 0
    by_predicate = defaultdict(list)
    for view in views: by_predicate[view['frame']['statements'][0]['predicate']].append(view)
    for predicate in sorted(by_predicate):
        anchors = by_predicate[predicate]
        for first in anchors:
            a = first['frame']['statements'][0]; ra = roles(a); na = _native_roles(first, graph)
            for second in anchors:
                if first['key'] == second['key']: continue
                b = second['frame']['statements'][0]; rb = roles(b); nb = _native_roles(second, graph)
                unmatched_context = set(ra) ^ set(rb)
                if unmatched_context - CONTEXT_ROLES:
                    rejected['anchor_role_signature_difference'] += 1; continue
                common = set(ra) & set(rb)
                changed = {r: (ra[r], rb[r]) for r in common if ra[r] != rb[r]}
                factors = set(changed) & CHANGED_ROLES
                if len(factors) != 1 or set(changed) - CHANGED_ROLES - CONTEXT_ROLES: continue
                shared_endpoint = common - set(changed) - CONTEXT_ROLES - CHANGED_ROLES
                if not shared_endpoint: continue
                same_source = first['native_key'][0] == second['native_key'][0]
                if same_source and any(na[r]['target'] != nb[r]['target'] for r in common - set(changed)):
                    rejected['same_name_different_native_entity'] += 1; continue
                factor = next(iter(factors))
                for donor in views:
                    steps += 1; require(steps <= LIMITS['search_steps'], 'Analogy search budget exceeded; no partial publication')
                    if donor['native_key'][0] != first['native_key'][0] or donor['key'] in (first['key'], second['key']): continue
                    q = donor['frame']['statements'][0]; rq = roles(q); nq = _native_roles(donor, graph)
                    if rq.get(factor) != ra[factor] or nq[factor]['target'] != na[factor]['target']: continue
                    if any(r not in rq or rq[r] != old or nq[r]['target'] != na[r]['target']
                           for r, (old, _) in changed.items()): continue
                    if q['predicate'] == predicate and rq == ra: continue
                    # У нового результата должна быть своя измеряемая роль, а не только новый текст предиката.
                    if not (set(rq) - CONTEXT_ROLES - CHANGED_ROLES): continue
                    substitutions = {old: new for old, new in changed.values()}
                    if len(substitutions) != len(changed): rejected['ambiguous_substitution'] += 1; continue
                    if any(value in substitutions and role not in changed for role, value in rq.items()):
                        rejected['unbound_repeated_participant'] += 1; continue
                    proposed = deepcopy(donor['frame']); head = proposed['statements'][0]
                    for row in head['roles']:
                        if row['role'] in changed: row['value'] = changed[row['role']][1]
                    if len(set(roles(head).values())) < len(set(rq.values())):
                        rejected['participant_collapse'] += 1; continue
                    reason, existing = _newness(head, known)
                    if reason:
                        rejected[reason] += 1
                        bid = fingerprint({'head': proposed, 'reason': reason, 'known': existing})
                        blocked[bid] = {'id': bid, 'reason': reason, 'proposed_frame': proposed, 'known_statement': existing}
                        continue
                    donor_role_diff = {r: {'anchor': ra.get(r), 'donor': rq.get(r)} for r in sorted(CONTEXT_ROLES & (set(ra) | set(rq)))
                                       if ra.get(r) != rq.get(r)}
                    context_changes = {r: {'donor': old, 'recipient': new} for r, (old, new) in sorted(changed.items()) if r in CONTEXT_ROLES}
                    obligations = {'anchor_scope_differences': _scope_diff(a['scope'], b['scope']),
                        'donor_scope_differences': _scope_diff(a['scope'], q['scope']),
                        'donor_context_role_differences': donor_role_diff, 'context_role_substitutions': context_changes,
                        'unmatched_anchor_context_roles': {r: {'donor': ra.get(r), 'recipient': rb.get(r)} for r in sorted(unmatched_context)},
                        'anchor_attribute_differences': _attrs_diff(a['attributes'], b['attributes']),
                        'donor_attribute_differences': _attrs_diff(a['attributes'], q['attributes']),
                        'donor_conditions_retained_not_recipient_protocol': True,
                        'cross_source_entity_identity_established': same_source,
                        'causal_response_transport_established': False}
                    # Область донора является условием предложения, а не фактом измерения у получателя.
                    head['scope']['modality'] = 'hypothesis; analogical response transport not established'
                    # Разные свидетельства одной гипотезы не занимают несколько мест фиксированного бюджета.
                    identity = fingerprint({'frame': proposed, 'recipient_article': second['native_key'][0]})
                    members = (first, second, donor)
                    witness = {'premises': [{'key': list(v['key']), 'native_key': list(v['native_key']),
                        'frame': deepcopy(v['frame']), 'projection_proof_id': v['projection_proof']['id'],
                        'native_roles': deepcopy(_native_roles(v, graph)),
                        'direction_operand_proof_id': v.get('direction_operand_proof', {}).get('id')} for v in members],
                        'substitutions': {r: {'from': old, 'to': new} for r, (old, new) in sorted(changed.items())},
                        'premise_publication_families': sorted({families[v['native_key'][0]] for v in members}),
                        'transport_obligations': deepcopy(obligations),
                        'author_asserted_rule': False}
                    candidate = candidates.setdefault(identity, {'id': identity, 'operator': VERSION,
                        'status': 'unvalidated_directional_analogy_hypothesis', 'frame': proposed,
                        'recipient_article': second['native_key'][0], 'donor_article': first['native_key'][0],
                        'observed_recipient_anchor_scope': deepcopy(b['scope']),
                        'proposed_scope_status': 'donor_conditions_retained_recipient_response_not_observed',
                        'transport_obligations': obligations, 'all_transport_obligations': [], 'witnesses': [],
                        'logical_entailment': False, 'new_measurement': False, 'conclusion_confirmed': False,
                        'effect_size': None, 'predicted_p_value': None, 'probability': None,
                        'conclusion_support_families': [], 'expert_validated': False})
                    if fingerprint(witness) not in {fingerprint(w) for w in candidate['witnesses']}: candidate['witnesses'].append(witness)
                    if obligations not in candidate['all_transport_obligations']:
                        candidate['all_transport_obligations'].append(deepcopy(obligations))
    for c in candidates.values():
        c['all_transport_obligations'].sort(key=lambda o: (_obligation_cost(o), fingerprint(o)))
        c['transport_obligations'] = deepcopy(c['all_transport_obligations'][0])
        c['ranking_obligation_cost'] = _obligation_cost(c['transport_obligations'])
    ordered = sorted(candidates.values(), key=lambda c: (c['ranking_obligation_cost'], c['id']))
    return {'all_candidates': ordered, 'ranked_candidates': ordered[:LIMITS['candidate_limit']],
            'search_steps': steps, 'rejection_counts': dict(rejected), 'known_or_tested_gaps': sorted(blocked.values(), key=lambda b: b['id'])}


def discover_from_licensed_parts(parts, graph, origins, families):
    parents, sources = _validate_inputs(parts, graph, origins)
    require(set(families) == set(sources), 'Exact source family mapping required')
    admitted = []; decisions = []; counts = Counter(); by_parent = defaultdict(list)
    for original_view in sorted(parts['part_views'], key=lambda v: v['key']):
        view = _direction_view(original_view)
        reason = _admission(view, graph, sources); counts[reason or 'admitted'] += 1
        decisions.append({'key': list(view['key']), 'native_key': list(view['native_key']), 'reason': reason})
        by_parent[tuple(view['native_key'])].append(reason)
        if reason is None: admitted.append(view)
    known = _known_statements(graph)
    result = _search(admitted, graph, sources, families, known)
    # Стрелки автора не разрешают аналогию: одинаковый поиск после удаления должен дать те же предложения.
    flat = {**graph, 'author_dependencies': [], 'visible_occurrence_edges': []}
    control = _search(admitted, flat, sources, families, known)
    require(result == control, 'Visible-dependency ablation changed an operator that does not use them')
    coverage = [{'article_id': key[0], 'knowledge_id': key[1], 'licensed_views': len(by_parent[key]),
        'admitted_views': sum(r is None for r in by_parent[key]), 'part_decisions': by_parent[key],
        'source_projection_reason': next(r['reason'] for r in parts['coverage']['coverage']
                                        if (r['article_id'], r['knowledge_id']) == key)} for key in sorted(parents)]
    return {'version': VERSION, 'limits': LIMITS, 'policy_ru': POLICY_RU, 'question': None,
        'canonical_blocks': len(parents), 'native_statements': len(known), 'licensed_parts': len(parts['part_views']),
        'admitted_parts': len(admitted), 'coverage': coverage, 'view_decisions': decisions, 'admission_counts': dict(counts),
        **result, 'proof_registry': {v['projection_proof']['id']: deepcopy(v['projection_proof']) for v in admitted},
        'direction_operand_proofs': [deepcopy(v['direction_operand_proof']) for v in admitted if 'direction_operand_proof' in v],
        'attribute_policy': {'memory_percent_fields': sorted(MEMORY_PERCENT_FIELDS), 'memory_p_fields': sorted(MEMORY_P_FIELDS),
            'protocol_numeric_fields': PROTOCOL_NUMERIC_FIELDS, 'source_qualification_fields': sorted(SOURCE_QUALIFICATION_FIELDS),
            'unknown_numeric_attribute_policy': 'reject_operand_without_guessing', 'protocol_quantities_preserved': True},
        'ablation': {'without_visible_dependencies_same_result': True, 'hidden_roles_retained': True,
            'graph_candidate_count': len(result['all_candidates']), 'flat_candidate_count': len(control['all_candidates'])},
        'model_calls': 0, 'target_read': False, 'future_results_scored': 0, 'accuracy': None,
        'confirmed_predictions': 0, 'scientific_success': False, 'graph_advantage_demonstrated': False}

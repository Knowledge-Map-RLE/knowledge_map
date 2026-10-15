"""Шаблоны семантических частей сохраняют родителя; новая совместная группа является гипотезой."""
from collections import Counter, defaultdict
from copy import deepcopy
from itertools import product

from domain.article_maps import fingerprint, require
from domain.whole_map_forecast import project, learn, bind, instantiate, LIMITS as FRAME_LIMITS
from domain.semantic_part_projection import project_parts
from domain.whole_map_provenance import partition_provenance
from domain.whole_map_numeric import project_numeric
from domain.statistical_context_audit import audit_models
from domain.evidence_origin_audit import validate_origins
from domain.whole_map_ablation import source_neighborhood_groups, permuted_groups
from domain.forecast_attribute_kinds import project_source_locators
from domain.qualitative_result_projection import project_qualitative_results
from domain.protocol_parameter_transfer import protocol_frame_identity
from domain.method_clause_projection import project_method_clauses
from domain.operation_role_bindings import project_role_bindings

VERSION = 'whole-map-semantic-part-forecast-8'
LIMITS = {'training_alignments': 200000, 'application_steps': 200000, 'candidate_limit': 20,
          'max_premise_parents': 3, 'minimum_primary_families': 2}


def participants(record):
    return {fingerprint(r['value']) for s in record['frame']['statements'] for r in s['roles']}


def connected(parts):
    sets = [participants(p) for p in parts]
    seen = {0}; changed = True
    while changed:
        changed = False
        for i, symbols in enumerate(sets):
            if i not in seen and any(symbols & sets[j] for j in seen):
                seen.add(i); changed = True
    return len(seen) == len(sets)


def align_groups(views, by_parent, groups):
    aligned = []; proofs = []; rejected = Counter(); steps = 0; seen = set()
    for body, head in groups:
        require(head in by_parent and all(p in by_parent for p in body), 'Unknown native development parent')
        require(head not in body and len(set(body)) == len(body), 'Repeated or self native premise')
        if not 1 <= len(body) <= LIMITS['max_premise_parents']:
            rejected['oversized_native_group'] += 1; continue
        if not by_parent[head] or any(not by_parent[p] for p in body):
            rejected['unlicensed_parent_parts'] += 1; continue
        for selected in product(*(by_parent[p] for p in body), by_parent[head]):
            steps += 1
            require(steps <= LIMITS['training_alignments'], 'Part alignment budget exceeded; no partial forecast')
            premises, conclusion = selected[:-1], selected[-1]
            if not connected([views[k] for k in selected]):
                rejected['disconnected_native_roles'] += 1; continue
            identity = fingerprint({'premises': premises, 'head': conclusion})
            if identity in seen: continue
            seen.add(identity); aligned.append((tuple(premises), conclusion))
            proofs.append({'premises': [list(k) for k in premises], 'head': list(conclusion),
                'native_development_group': {'premises': [list(k) for k in body], 'head': list(head)},
                'status': 'candidate_part_alignment_of_author_parent_group',
                'source_asserts_this_part_specific_rule': False, 'deductive_entailment': False,
                'reason_ru': 'Части логически допустимы, но авторский переход относится к полным блокам. '
                             'Сопоставление частей проверяется как статистическая гипотеза, не как правило автора.'})
    return aligned, {'alignments': proofs, 'steps': steps, 'rejected': dict(rejected)}


def primary_support(rules, views, origins):
    rows = []; admitted = []
    for rule in rules:
        primary = set(); secondary = set(); examples = []
        for example in rule['examples']:
            v = views[tuple(example['head'])]; native = v['native_key']
            source = origins['sources'][native[0]]
            annotation = v['projection_proof']['origin']
            is_primary = source['document_kind'] == 'primary_study' and annotation['origin'] == 'primary_result'
            if is_primary: primary.add(source['dataset_family'])
            else: secondary.add(native[0])
            examples.append({'part_head': list(v['key']), 'native_head': list(native),
                'statement_id': annotation['statement_id'], 'origin': annotation['origin'],
                'declared_primary_family': source['dataset_family'] if is_primary else None,
                'full_parent_retained': True})
        accepted = len(primary) >= LIMITS['minimum_primary_families']
        rows.append({'rule_id': rule['id'], 'primary_families': sorted(primary), 'other_sources': sorted(secondary),
            'examples': examples, 'minimum_primary_support_declared': accepted, 'expert_validated': False,
            'logical_entailment': False, 'participant_independence_certified': False})
        if accepted: admitted.append({**deepcopy(rule), 'primary_families': sorted(primary)})
    return admitted, rows


def apply_templates(views, by_parent, rules, native_groups, known, graph_mode):
    eligible = sorted(views.values(), key=lambda r: r['key'])
    source_edges = {(p, head) for body, head in native_groups for p in body}
    inventory = defaultdict(set)
    for v in views.values(): inventory[v['key'][0]].update(participants(v))
    pool = {}; rejected = Counter(); steps = 0
    for rule in rules:
        def walk(position, bindings, chosen):
            nonlocal steps
            if position == len(rule['body']):
                native = [v['native_key'] for v in chosen]
                if graph_mode and any((native[a], native[b]) not in source_edges for a, b in rule['internal_edges']):
                    rejected['missing_learned_internal_dependency'] += 1; return
                if any('constant' in r['value'] and fingerprint(r['value']['constant']) not in inventory[native[0][0]]
                       for s in rule['head']['statements'] for r in s['roles']):
                    rejected['head_constant_not_grounded'] += 1; return
                frame = instantiate(rule['head'], bindings); identity = fingerprint(frame)
                semantic_identity = protocol_frame_identity(frame)
                if semantic_identity in known:
                    rejected['known_part_conclusion'] += 1; return
                candidate = {'id': identity, 'frame': frame, 'rule_id': rule['id'],
                    'status': 'empirical_part_template_hypothesis', 'primary_families': rule['primary_families'],
                    'premises': [{'part_key': list(v['key']), 'native_key': list(v['native_key']),
                        'run_id': v['run_id'], 'projection_proof': deepcopy(v['projection_proof'])} for v in chosen],
                    'new_joint_group': {'source': 'proposed_by_learned_statistical_operator',
                        'all_selected_parents_required_by_template': True, 'author_asserted_group': False,
                        'known_author_group_required': False},
                    'logical_entailment': False, 'causality_asserted': False,
                    'independent_replication_certified': False, 'expert_validated': False}
                prior = pool.get(semantic_identity)
                if prior is None or (-len(candidate['primary_families']), rule['id']) < (-len(prior['primary_families']), prior['rule_id']):
                    pool[semantic_identity] = candidate
                return
            for v in eligible:
                steps += 1
                require(steps <= LIMITS['application_steps'], 'Part application budget exceeded; no partial forecast')
                # Две лицензированные части одной конъюнкции могут быть совместными входами.
                # Они не объявляются двумя независимыми источниками или двумя репликациями.
                if chosen and (v['key'][0] != chosen[0]['key'][0] or v['key'] in {p['key'] for p in chosen}): continue
                matched = bind(rule['body'][position], v['frame'], bindings, v)
                if matched is not None: walk(position + 1, matched, [*chosen, v])
        walk(0, {}, [])
    ordered = sorted(pool.values(), key=lambda c: (-len(c['primary_families']), len(c['premises']), c['id']))
    return ordered[:LIMITS['candidate_limit']], {'pool': len(ordered), 'steps': steps, 'rejected': dict(rejected)}


def forecast_parts(maps, families, context_audit, model_audit, origin_audit, compound_licenses=None, protocol_parameters=True, method_clauses=None, role_bindings=None):
    require(isinstance(protocol_parameters, bool), 'Explicit protocol operator mode must be boolean')
    require(set(families) == {m['article_id'] for m in maps}, 'Exact publication family registry required')
    origins = validate_origins(maps, origin_audit)
    originals, groups, _ = project(maps, context_audit)
    for m in maps:
        for k in m['graph']['knowledge']:
            originals[m['article_id'], k['knowledge_id']]['native_knowledge'] = deepcopy(k)
    records = deepcopy(originals)
    for key, entry in audit_models(maps, model_audit).items(): records[key]['model_context'] = entry
    records, provenance = partition_provenance(records, families)
    records, numeric = project_numeric(records)
    records, locator_metadata = project_source_locators(records, origins)
    records, qualitative_results = project_qualitative_results(records, origins)
    views, by_parent, known, coverage = project_parts(records, originals, origins, compound_licenses)
    method_projection = None
    if method_clauses is not None:
        views, by_parent, known, method_projection = project_method_clauses(views, by_parent, known, maps, method_clauses)
    role_projection = None
    if role_bindings is not None:
        views, by_parent, known, role_projection = project_role_bindings(views, by_parent, known, maps, groups, role_bindings)
    choices = {'graph': groups, 'source_neighborhood_without_dependencies': source_neighborhood_groups(originals),
               'permuted_dependencies': permuted_groups(originals, groups)}
    learned = {}; diagnostics = {}; primary = {}; predictions = {}
    for mode, native_groups in choices.items():
        aligned, alignment = align_groups(views, by_parent, native_groups)
        rules, learning = learn(views, aligned, families, protocol_parameters)
        accepted, support = primary_support(rules, views, origins)
        # Все неподдержанные варианты также получают раздельный учёт происхождения.
        _, unsupported_support = primary_support(learning['unsupported_rules'], views, origins)
        learned[mode] = {'publication_supported_rules': rules, 'primary_supported_rules': accepted,
                         'learning': learning, 'unsupported_origin_support': unsupported_support}
        primary[mode] = support
        predictions[mode], application = apply_templates(views, by_parent, accepted, native_groups, known,
                                                         mode != 'source_neighborhood_without_dependencies')
        diagnostics[mode] = {'alignment': alignment, 'application': application}
        if mode == 'graph':
            predictions['same_rules_without_dependencies'], flat = apply_templates(views, by_parent, accepted, native_groups, known, False)
            diagnostics['same_rules_without_dependencies'] = {'application': flat, 'same_rules': True}
    return {'version': VERSION if compound_licenses is None else VERSION + '+contrast-clause-license-1',
        'question': None, 'limits': LIMITS, 'frame_learner_limits': FRAME_LIMITS,
        'protocol_parameters_enabled': protocol_parameters,
        'canonical_blocks': len(originals), 'licensed_parts': len(views), 'coverage': coverage,
        'part_views': list(views.values()), 'learning_by_mode': learned, 'primary_support_by_mode': primary,
        'predictions': predictions, 'diagnostics': diagnostics,
        'numeric_consequences': numeric, 'provenance_partition': provenance, 'source_locator_metadata': locator_metadata,
        'qualitative_result_projection': qualitative_results,
        'method_clause_projection': method_projection,
        'operation_role_bindings': role_projection,
        'model_calls': 0, 'target_read': False, 'scientific_success': False, 'graph_advantage_demonstrated': False,
        'policy_ru': 'Полный корпус без вопроса и тематического фильтра. Части одиночных блоков и конъюнкций '
                     'сохраняют полный родитель. Источник не объявляется автором части-специфического правила. '
                     'Новый совместный вход — проверяемая статистическая гипотеза; внутренние направленные связи '
                     'контролируются отдельно. Контекст и неизвестные числа не исправляются ради прогноза.'}

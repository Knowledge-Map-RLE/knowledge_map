"""Типизированный контекст запрещает смешение моделей; новый протокол остаётся предложением."""
from collections import Counter
from copy import deepcopy
from hashlib import sha256

from domain.article_maps import fingerprint, require
from domain.licensed_part_analogy import VERSION as ANALOGY_VERSION
from domain.analogy_transport import CHANGED_ROLES, CONTEXT_ROLES

VERSION = 'source-bound-analogy-protocol-reconciliation-1'
PROTECTED = ('species', 'disease_model', 'challenge_anchor')
DIMENSIONS = (*PROTECTED, 'target_mechanism', 'route', 'tissue', 'assessment', 'recipe', 'genotype', 'age', 'sex')
REQUIRED_DESIGN = ('species', 'disease_model', 'challenge_anchor', 'target_mechanism', 'route', 'recipe', 'genotype')


def _endpoint_roles(premise):
    # В проект измерения не копируются генетическое воздействие и популяция донора.
    return [deepcopy(r) for r in premise['frame']['statements'][0]['roles']
            if r['role'] not in CHANGED_ROLES | CONTEXT_ROLES]


def _validate_annotation(forecast, graph, audit):
    require(forecast['version'] == ANALOGY_VERSION and forecast['question'] is None
            and forecast['model_calls'] == 0 and forecast['target_read'] is False, 'Source-only analogy snapshot required')
    require(audit['version'] == VERSION and audit['author'] == 'Codex' and audit['expert_validated'] is False
            and audit['model_calls'] == 0 and audit['target_read'] is False, 'Source-bound Codex context annotation required')
    require(audit['forecast_run_id'] == forecast['run_id'] and audit['forecast_sha256'] == fingerprint(forecast)
            and audit['semantic_graph_sha256'] == fingerprint(graph), 'Context input binding differs')
    used = {p['projection_proof_id'] for c in forecast['all_candidates'] for w in c['witnesses'] for p in w['premises']}
    require(len({c['id'] for c in forecast['all_candidates']}) == len(forecast['all_candidates']), 'Duplicate candidate identity')
    ranked_ids = [c['id'] for c in forecast['ranked_candidates']]
    require(len(set(ranked_ids)) == len(ranked_ids) and set(ranked_ids) <= {c['id'] for c in forecast['all_candidates']},
            'Invalid frozen budget')
    rows = {r['projection_proof_id']: r for r in audit['contexts']}
    require(len(rows) == len(audit['contexts']) and set(rows) == used, 'Complete used-statement context coverage required')
    for key, row in rows.items():
        proof = forecast['proof_registry'][key]
        require(row['parent_key'] == proof['parent_key'] and row['native_statement_id'] == proof['native_statement_id']
                and row['projection_proof_sha256'] == fingerprint(proof), 'Source part binding differs')
        require(set(row['dimensions']) == set(DIMENSIONS) and row['reason_ru'], 'Explicit typed dimensions required')
        for dimension, value in row['dimensions'].items():
            require(set(value) == {'value', 'status', 'evidence'} and value['status'] in {'source_stated', 'unknown'},
                    'Source fact or explicit unknown required')
            if value['status'] == 'unknown':
                require(value['value'] is None and not value['evidence'], 'Unknown dimension cannot acquire a guessed value')
                continue
            require(value['value'] is not None and value['evidence'], 'Grounded typed context value required')
            for ref in value['evidence']:
                require(ref['source_unit'] in graph['source_units'], 'Unknown context source unit')
                unit = graph['source_units'][ref['source_unit']]
                require(unit['article_id'] == row['parent_key'][0] and ref['source_sha256'] == unit['source_sha256']
                        and ref['unit_sha256'] == unit['sha256'] and ref['quote'] and ref['quote'] in unit['text']
                        and sha256(unit['text'].encode()).hexdigest() == unit['sha256']
                        and len(unit['text']) == unit['end'] - unit['start'], 'Context evidence or Unicode fragment differs')
    proposals = {r['projection_proof_id']: r for r in audit['recipient_designs']}
    recipients = {w['premises'][1]['projection_proof_id'] for c in forecast['all_candidates'] for w in c['witnesses']}
    require(len(proposals) == len(audit['recipient_designs']) and set(proposals) == recipients,
            'Complete recipient design coverage required')
    for key, row in proposals.items():
        require(row['status'] in {'source_recipe_design_proposal', 'no_design_proposed'} and row['reason_ru'], 'Explicit design status required')
        if row['status'] == 'no_design_proposed':
            require(row['design'] is None, 'Unresolved design cannot contain an implicit fallback'); continue
        require(row['status'] == 'source_recipe_design_proposal' and row['design']['observed_recipient_response'] is False
                and row['design']['is_original_unique_dose_established'] is False
                and row['design']['condition_on_predicted_response'] is False, 'Proposed protocol is not an observed target fact')
        require(row['design']['recipe'] == rows[key]['dimensions']['recipe']['value'], 'Design must preserve the explicit source recipe')
        require(row['design']['target_mechanism'] == rows[key]['dimensions']['target_mechanism']['value'], 'Target identity changed')
        require(all(rows[key]['dimensions'][k]['status'] == 'source_stated' for k in REQUIRED_DESIGN),
                'Recipient design requires explicit model, target, route, recipe and genotype')
        target = row['design']['target_mechanism']
        require(isinstance(target, dict) and {'mechanism', 'target_species', 'expressed_receptor_species'} <= set(target),
                'Explicit drug target species required')
    return rows, proposals


def reconcile_protocols(forecast, graph, audit):
    contexts, designs = _validate_annotation(forecast, graph, audit)
    reviews = []; counts = Counter(); ranked = {c['id']: i + 1 for i, c in enumerate(forecast['ranked_candidates'])}
    for candidate in forecast['all_candidates']:
        witnesses = []
        for w in candidate['witnesses']:
            keys = [p['projection_proof_id'] for p in w['premises']]
            a, b, q = [contexts[k]['dimensions'] for k in keys]
            blockers = []; unknowns = []; differences = []
            for dimension in PROTECTED:
                triplet = [r[dimension] for r in (a, b, q)]
                if any(v['status'] == 'unknown' for v in triplet): unknowns.append(dimension); continue
                if len({fingerprint(v['value']) for v in triplet}) != 1:
                    blockers.append({'dimension': dimension, 'donor_anchor': triplet[0]['value'],
                        'recipient_anchor': triplet[1]['value'], 'donor_response': triplet[2]['value']})
            # Одинаковая подпись гена в разных тканях не устанавливает один общий опорный ответ.
            if any(r['tissue']['status'] == 'unknown' for r in (a, b)):
                # Поведенческий тест не является измерением ткани; одинаковый явный тест сохраняется.
                tests = [{r['value'] for r in p['frame']['statements'][0]['roles'] if r['role'] == 'test'}
                         for p in w['premises'][:2]]
                if not (a['tissue']['status'] == b['tissue']['status'] == 'unknown' and tests[0] and tests[0] == tests[1]):
                    unknowns.append('anchor_tissue')
            elif a['tissue']['value'] != b['tissue']['value']:
                blockers.append({'dimension': 'anchor_tissue', 'donor_anchor': a['tissue']['value'],
                    'recipient_anchor': b['tissue']['value']})
            for dimension in ('route', 'target_mechanism', 'genotype', 'assessment', 'recipe'):
                if any(r[dimension]['status'] == 'unknown' for r in (a, b, q)): unknowns.append(dimension)
                if a[dimension]['value'] != b[dimension]['value'] or a[dimension]['value'] != q[dimension]['value']:
                    differences.append({'dimension': dimension, 'donor_anchor': a[dimension]['value'],
                        'recipient_anchor': b[dimension]['value'], 'donor_response': q[dimension]['value']})
            b_target = b['target_mechanism']['value']
            if b_target is not None and b_target['mechanism'] == 'pharmacological_antagonism':
                if b_target['target_species'] != b_target['expressed_receptor_species']:
                    blockers.append({'dimension': 'drug_target_not_expressed', 'target': deepcopy(b_target)})
            design = designs[keys[1]]
            if design['status'] == 'no_design_proposed': unknowns.append('recipient_design')
            for dimension in ('assessment', 'tissue'):
                if q[dimension]['status'] == 'unknown': unknowns.append('measurement_' + dimension)
            endpoints = _endpoint_roles(w['premises'][2])
            if not endpoints: unknowns.append('measurement_endpoint')
            proposed = None
            required_unknowns = set(PROTECTED) | {'anchor_tissue', 'measurement_assessment', 'measurement_tissue', 'measurement_endpoint'}
            if not blockers and not (set(unknowns) & required_unknowns) and design['status'] == 'source_recipe_design_proposal':
                proposed = deepcopy(design['design'])
                proposed['measurement'] = {'endpoint_roles': endpoints,
                    'tissue': deepcopy(q['tissue']['value']), 'assessment': deepcopy(q['assessment']['value']),
                    'status': 'proposed_measurement_not_observed_recipient_result',
                    'assessment_from_donor_is_design_choice': True}
                proposed['population'] = {'genotype': deepcopy(b['genotype']['value']), 'species': b['species']['value'],
                    'age': deepcopy(b['age']['value']), 'sex': b['sex']['value'], 'unknown_demographics_preserved': True}
                proposed['demographic_registration_required'] = any(b[k]['status'] == 'unknown' for k in ('age', 'sex'))
                proposed['challenge'] = deepcopy(b['disease_model']['value'])
                proposed['hypothesis_frame_unmodified'] = deepcopy(candidate['frame'])
                proposed['source_conditions_not_declared_recipient_facts'] = True
                proposed['uncertain_assumptions'] = ['analogical_response_transfer_not_established']
                for dimension in ('target_mechanism', 'genotype', 'assessment', 'recipe', 'route'):
                    if a[dimension]['value'] != b[dimension]['value'] or q[dimension]['value'] != b[dimension]['value']:
                        proposed['uncertain_assumptions'].append(dimension + '_response_transfer_not_established')
                proposed['scope_equivalence_established'] = False
                proposed['future_control_eligible_without_scope_audit'] = False
            status = ('blocked_context_mixture' if blockers else 'unresolved_source_context' if proposed is None
                      else 'testable_design_hypothesis_not_confirmed')
            witnesses.append({'premise_context_keys': keys, 'status': status, 'blocking_differences': blockers,
                'unknown_dimensions': sorted(set(unknowns)), 'preserved_differences': differences,
                'proposed_protocol': proposed, 'conclusion_confirmed': False, 'causal_transfer_established': False})
        valid = [w for w in witnesses if w['status'] == 'testable_design_hypothesis_not_confirmed']
        status = ('testable_design_hypothesis_not_confirmed' if valid else 'blocked_context_mixture'
                  if all(w['status'] == 'blocked_context_mixture' for w in witnesses) else 'unresolved_source_context')
        counts[status] += 1
        reviews.append({'candidate_id': candidate['id'], 'original_rank': ranked.get(candidate['id']), 'status': status,
            'original_frame': deepcopy(candidate['frame']), 'witness_reviews': witnesses,
            'included_in_original_budget': candidate['id'] in ranked, 'conclusion_confirmed': False})
    # После отказов места не заполняются новыми кандидатами за пределами исходных двадцати.
    slots = sorted([r for r in reviews if r['included_in_original_budget']], key=lambda r: r['original_rank'])
    return {'version': VERSION, 'question': None, 'forecast_run_id': forecast['run_id'], 'candidate_reviews': reviews,
        'counts': dict(counts), 'original_budget_slots': slots, 'original_budget_preserved': True,
        'outside_budget_promoted': False, 'annotated_source_statements': len(contexts),
        'source_forecast_parent_coverage': forecast['canonical_blocks'], 'all_candidates_reviewed': len(reviews),
        'context_annotation': deepcopy(audit), 'model_calls': 0, 'target_read': False,
        'new_confirmed_predictions': 0, 'future_results_scored': 0, 'accuracy': None,
        'scientific_success': False, 'graph_advantage_demonstrated': False,
        'policy_ru': 'Согласованный проект опыта не подтверждает ожидаемый ответ. Защищённые модель и '
            'событие начала времени не объединяются без источникового основания. Дозировка выбирается '
            'явно как рецепт проектируемого опыта; неоднозначность исходных подписей сохраняется. '
            'Неизвестные демографические условия остаются неизвестными. Места отказов не заменяются.'}

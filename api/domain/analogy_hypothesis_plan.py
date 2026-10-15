"""Направленная гипотеза допускает неизвестность, но сохраняет проверяемые условия."""
from copy import deepcopy
from datetime import datetime

from domain.article_maps import fingerprint, require

VERSION = 'uncertain-analogy-hypothesis-plan-1'
OPERATORS = {
    'induction attenuated': 'lower_induction',
    'cell count reduced after intervention': 'lower_cell_count',
    'morphology preserved after intervention': 'better_preserved_morphology',
}


def generate_hypothesis_plan(forecast, protocol_audit, plan):
    require(forecast['question'] is None and forecast['target_read'] is False and forecast['model_calls'] == 0,
            'Whole-map source-only analogy forecast required')
    require(protocol_audit['forecast_run_id'] == forecast['run_id'] and
            protocol_audit['binding']['forecast_sha256'] == fingerprint(forecast), 'Protocol forecast differs')
    require(protocol_audit['target_read'] is False and protocol_audit['model_calls'] == 0 and
            protocol_audit['confirmed_transfers'] == 0, 'Unestablished protocol audit required')
    require(plan['version'] == VERSION and plan['author'] == 'Codex' and plan['expert_validated'] is False,
            'Explicit hypothesis annotation required')
    require(plan['forecast_sha256'] == fingerprint(forecast) and plan['protocol_audit_sha256'] == fingerprint(protocol_audit),
            'Hypothesis input binding differs')
    require(plan['target_read'] is False and plan['model_calls'] == 0 and plan['question'] is None,
            'Question or target outcome cannot choose these hypotheses')
    stamp = datetime.fromisoformat(plan['registered_at_utc'])
    require(stamp.utcoffset() is not None, 'Actual registration time with timezone required')
    require(plan['historical_debug_corpus'] is True and plan['prospective_scientific_validation'] is False,
            'Debug corpus is not a prospective independent validation')
    candidates = {c['id']: c for c in forecast['transport_tasks']}
    reviews = {r['candidate_id']: r for r in protocol_audit['candidate_reviews']}
    rows = plan['candidate_protocols']
    require(len(rows) == len(candidates) and {r['candidate_id'] for r in rows} == set(candidates),
            'Every generated analogy task must receive a protocol; no favourable subset')
    require(bool(plan['evaluation_policy']['unmeasured_is_not_refuted']) and
            plan['evaluation_policy']['statistical_nondetection'] == 'inconclusive' and
            plan['evaluation_policy']['unknown_context'] == 'not_confirmed' and
            plan['evaluation_policy']['repeated_known_outcome'] == 'exclude', 'Explicit qualitative evaluation policy required')
    require(plan['evaluation_policy']['condition_on_predicted_response'] is False and
            plan['evaluation_policy']['unit_of_scoring'] == 'prespecified_endpoint',
            'Forecast eligibility cannot assume the predicted outcome')
    require(plan['evaluation_policy']['candidate_budget'] == len(candidates), 'Fixed complete candidate budget required')
    hypotheses = []
    for row in rows:
        candidate = candidates[row['candidate_id']]
        base = candidate['proposed_qualitative_frame']
        require(row['frame_sha256'] == fingerprint(base) and
                row['obligations_sha256'] == fingerprint(candidate['transport_obligations']), 'Analogy context changed')
        require(base['logic'] == 'single' and len(base['statements']) == 1 and
                base['statements'][0]['predicate'] in OPERATORS and not base['statements'][0]['negated'],
                'Registered positive qualitative analogy operator required')
        statement = base['statements'][0]
        require(statement['attributes'] == [] and not candidate['logical_entailment'] and
                not candidate['causal_transport_established'], 'Unestablished analogy cannot transfer numerical results')
        require(row['review_sha256'] == fingerprint(reviews[candidate['id']]), 'Protocol review changed')
        require(reviews[candidate['id']]['decision'] == 'transfer_not_established', 'Protocol uncertainty must remain')
        require(row['unknown_dimensions'] == reviews[candidate['id']]['unresolved'], 'Unresolved dimensions erased')
        protocol = row['proposed_protocol']
        require(protocol['status'] == 'proposed_design_not_observed_fact' and protocol['comparator'] and
                protocol['intervention'] and protocol['population'] and protocol['challenge'] and
                protocol['measurement'] and protocol['assessment_time'] and protocol['design_choices'],
                'Testable recipient protocol required')
        roles = {r['role']: r['value'] for r in statement['roles']}
        require(protocol['intervention']['identity'] == roles['intervention'] and
                protocol['population']['source_population_label'] == roles['population'], 'Recipient identity changed')
        require(protocol['assessment_time']['source_scope'] == statement['scope']['time'], 'Outcome phase changed')
        endpoint_role = next((k for k in ('gene', 'outcome', 'tissue') if k in roles), None)
        require(endpoint_role is not None and protocol['measurement']['endpoint_role'] == endpoint_role and
                protocol['measurement']['endpoint_value'] == roles[endpoint_role], 'Predicted endpoint changed')
        require(protocol['evidence_findings'] and set(protocol['evidence_findings']) <= set(reviews[candidate['id']]['findings']),
                'Protocol evidence must remain explicit')
        require(row['statement_ru'] and row['falsification_ru'] and row['assumptions_ru'] and
                row['probability'] is None and row['effect_size'] is None and row['predicted_p_value'] is None,
                'Directional hypothesis without fabricated confidence or significance required')
        frame = deepcopy(base)
        frame['statements'][0]['scope']['modality'] = 'hypothesis; transfer not established'
        head = {'version': VERSION, 'analogy_candidate_id': candidate['id'], 'knowledge_status': 'hypothesis',
            'knowledge_kind': 'state', 'frame': frame, 'unmodified_analogy_frame': deepcopy(base),
            'direction': OPERATORS[statement['predicate']], 'statement_ru': row['statement_ru'],
            'falsification_ru': row['falsification_ru'], 'assumptions_ru': row['assumptions_ru'],
            'proposed_protocol': deepcopy(protocol), 'unknown_dimensions': deepcopy(row['unknown_dimensions']),
            'transport_obligations': deepcopy(candidate['transport_obligations']),
            'witnesses': deepcopy(candidate['witnesses']), 'probability': None, 'effect_size': None,
            'predicted_p_value': None, 'logical_entailment': False, 'causal_transfer_established': False,
            'confirmed': False, 'expert_validated': False}
        hypotheses.append({'id': fingerprint(head), **head})
    require(not forecast['hypotheses'], 'Plan handles task hypotheses only; scope-matched pool must be scored separately')
    return {'version': VERSION, 'question': None, 'hypotheses': hypotheses, 'hypothesis_count': len(hypotheses),
        'canonical_blocks_searched': forecast['canonical_blocks'], 'native_statements_searched': forecast['native_statements'],
        'source_registry_unchanged': True, 'canonical_maps_changed': False,
        'generation_scope_ru': 'Полный поиск исходного оператора аналогии; план задаёт условия для всех полученных задач. '
                               'Это один оператор, не полное покрытие всех возможных операций мышления.',
        'registration': deepcopy(plan), 'future_results_scored': 0, 'confirmed_predictions': 0,
        'accuracy': None, 'scientific_success': False, 'graph_advantage_demonstrated': False,
        'ablation': deepcopy(forecast['ablation']), 'model_calls': 0, 'target_read': False}

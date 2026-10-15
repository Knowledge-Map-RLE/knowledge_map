"""Внешняя гипотеза отделена от совпадения направления и временного подтверждения."""
from copy import deepcopy

from domain.article_maps import fingerprint, require
from domain.conditional_operation_transfer import forecast_transfers

VERSION = 'external-source-operation-transfer-1'
PACKET_FIELDS = {'version', 'author', 'expert_validated', 'source_packet_sha256', 'source_sha256',
                 'receivers', 'method_evidence', 'model_calls', 'results_previously_disclosed',
                 'blind_control', 'temporal_train_test_split', 'author_script_sha256', 'scope_ru'}


def forecast_external(training, packet):
    require(set(packet) == PACKET_FIELDS, 'External receiver packet contains result or unsupported fields')
    require(packet['version'] == 'source-method-only-receivers-1' and packet['model_calls'] == 0
            and packet['results_previously_disclosed'] is True and packet['blind_control'] is False,
            'External source exposure must be explicit')
    receivers = packet['receivers']
    require(packet['author'] == 'Codex' and packet['expert_validated'] is False
            and packet['temporal_train_test_split'] is False,
            'External retrospective annotation policy differs')
    require(len({r['id'] for r in receivers}) == len(receivers)
            and {q['receiver_id'] for q in packet['method_evidence']} == {r['id'] for r in receivers}
            and len(packet['method_evidence']) == len(receivers)
            and all(r['source_sha256'] == packet['source_sha256'] for r in receivers),
            'External methods or source identity differ')
    articles = set(training['source_article_ids'])
    require(articles and {c['article_id'] for c in training['cases']} <= articles,
            'Complete explicit training article registry required')
    families = {c['primary_family'] for c in training['cases']}
    require(receivers and all(r['article_id'] not in articles and r['primary_family'] not in families for r in receivers),
            'External receiving study is already in training')
    result = forecast_transfers(training['cases'], receivers, training['author_groups'], training['coverage'])
    result.update(version=VERSION, transfer_version=result['version'],
        external_source_packet_sha256=fingerprint(packet), external_results_used_in_training=False,
        target_question=None, temporal_prediction_specified=False, temporal_train_test_split=packet['temporal_train_test_split'],
        scope_ru='Обучение по прежнему явному корпусу. Внешняя статья даёт только два действия и контекст. '
                 'Это ретроспективная проверка, а не слепое предсказание ранее неизвестного результата.')
    return result


def evaluate_external(forecast, outcomes):
    require(forecast['version'] == VERSION and forecast['external_results_used_in_training'] is False,
            'Invalid external forecast')
    require(set(outcomes) == {r['id'] for r in forecast['receivers']}, 'External evaluation source differs')
    modes = {}
    for mode, folds in forecast['modes'].items():
        rows = []
        for fold in folds:
            outcome = outcomes[fold['receiver_id']]
            require(outcome['source_sha256'] == next(r['source_sha256'] for r in forecast['receivers']
                if r['id'] == fold['receiver_id']) and outcome['evidence'] and outcome['limitations_ru'],
                'Outcome source or limitations missing')
            for candidate in fold['predictions']:
                direction_match = all(candidate['head'][k] == outcome[k] for k in ('qualitative_direction', 'outcome_class'))
                # Общий знак без временного контракта не подтверждает длительность эффекта.
                temporal_specified = 'temporal_scope' in candidate['head']
                rows.append({'prediction_id': candidate['id'], 'receiver_id': fold['receiver_id'],
                    'coarse_direction_matches': direction_match,
                    'relation': 'direction_match_temporal_scope_unresolved' if direction_match and not temporal_specified
                                else 'direction_mismatch' if not direction_match else 'requires_typed_temporal_evaluator',
                    'temporal_prediction_specified': temporal_specified, 'full_fact_equivalence': False,
                    'independent_scientific_confirmation': False, 'outcome': deepcopy(outcome)})
        modes[mode] = rows
    return {'version': VERSION, 'forecast_sha256': fingerprint(forecast), 'modes': modes,
        'new_scientific_knowledge_confirmed': False, 'graph_advantage_demonstrated': False,
        'results_previously_disclosed': True, 'blind_control': False, 'expert_validated': False, 'model_calls': 0,
        'policy_ru': 'Совпадение общего направления учитывается диагностически. Без временного контракта '
                     'нельзя засчитать устойчивость эффекта или полную совместимость научного утверждения.'}

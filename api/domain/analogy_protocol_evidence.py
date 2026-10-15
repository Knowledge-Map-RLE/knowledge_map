"""Опора на прошлый протокол не удостоверяет перенос нового эффекта между моделями."""
from copy import deepcopy
from hashlib import sha256
from datetime import date

from domain.article_maps import fingerprint, require

VERSION = 'source-bound-analogy-protocol-evidence-1'
KINDS = {'binding_context', 'delivery_context', 'context_counterexample', 'protocol_ambiguity', 'unresolved_mechanism'}


def assess_protocol_evidence(forecast, packets, audit):
    require(forecast['question'] is None and forecast['model_calls'] == 0 and forecast['target_read'] is False,
            'Source-only analogy forecast required')
    require(audit['version'] == VERSION and audit['author'] == 'Codex' and audit['expert_validated'] is False
            and audit['model_calls'] == 0, 'Explicit protocol annotation version and status required')
    require(audit['forecast_run_id'] == forecast['run_id'] and audit['forecast_sha256'] == fingerprint(forecast),
            'Protocol annotation forecast binding differs')
    require(set(audit['sources']) == set(packets), 'Exact protocol source registry required')
    cutoff = forecast['binding']['metadata']['training_cutoff']
    require(date.fromisoformat(cutoff).isoformat() == cutoff, 'Exact source protocol cutoff required')
    for sid, packet in packets.items():
        source = packet['source']; binding = audit['sources'][sid]
        published = binding['published_on']
        require(type(published) is str and date.fromisoformat(published).isoformat() == published and published <= cutoff,
                'Future or imprecise protocol evidence source')
        require(fingerprint(packet) == binding['packet_sha256'] and source['sha256'] == binding['source_sha256'],
                'Protocol packet changed')
        require(sha256(source['text'].encode()).hexdigest() == source['sha256'], 'Protocol full source changed')
        require(source['offset_encoding'] == 'unicode_codepoints', 'Protocol Unicode coordinates required')
        require(source['sha256'] != 'f7df96ff746be4a60a6930ff2c5c25435725d0591dfe1f492259624b2d7c0bc8',
                'Excluded target source in protocol evidence')
        units = {u['id']: u for u in source['units']}
        require(len(units) == len(source['units']), 'Repeated protocol source unit')
        require(all(type(u['start']) is int and type(u['end']) is int and 0 <= u['start'] < u['end'] <= source['content_end']
                    and source['text'][u['start']:u['end']] == u['text'] for u in units.values()), 'Protocol source unit differs')
    findings = {f['id']: f for f in audit['findings']}
    require(len(findings) == len(audit['findings']) and bool(findings), 'Distinct nonempty protocol findings required')
    for finding in findings.values():
        require(finding['kind'] in KINDS and bool(finding['statement_ru']) and bool(finding['scope'])
                and bool(finding['evidence']), 'Explicit protocol finding and scope required')
        require(finding['causal_transfer_established'] is False and finding['clinical_efficacy_established'] is False,
                'Protocol finding does not establish target efficacy')
        for e in finding['evidence']:
            require(e['source_id'] in packets, 'Unknown protocol evidence source')
            source = packets[e['source_id']]['source']; units = {u['id']: u for u in source['units']}
            require(e['unit_id'] in units, 'Unknown protocol evidence unit')
            unit = units[e['unit_id']]
            require(e['start'] == unit['start'] and e['end'] == unit['end'] and e['text'] == unit['text']
                    and e['sha256'] == sha256(unit['text'].encode()).hexdigest(), 'Protocol evidence fragment changed')
    candidates = {c['id']: c for c in forecast['transport_tasks']}
    rows = audit['candidate_reviews']
    require(len(rows) == len(candidates) and {r['candidate_id'] for r in rows} == set(candidates),
            'Complete protocol candidate review required')
    for row in rows:
        candidate = candidates[row['candidate_id']]
        require(row['obligations_sha256'] == fingerprint(candidate['transport_obligations']),
                'Protocol obligations changed')
        require(row['decision'] == 'transfer_not_established' and row['remains_research_task'] is True,
                'Source protocol support alone cannot promote an empirical forecast')
        require(bool(row['findings']) and len(set(row['findings'])) == len(row['findings'])
                and set(row['findings']) <= set(findings), 'Unknown or repeated protocol finding')
        require(bool(row['unresolved']) and bool(row['reason_ru']), 'Unresolved target application must remain explicit')
        require(all(type(v) is str and v for v in row['unresolved']), 'Explicit unresolved protocol dimensions required')
    return {'version': VERSION, 'forecast_run_id': forecast['run_id'], 'source_count': len(packets),
        'findings': deepcopy(audit['findings']), 'candidate_reviews': deepcopy(rows),
        'candidate_count': len(candidates), 'confirmed_transfers': 0, 'new_empirical_predictions': 0,
        'model_calls': 0, 'target_read': False, 'scientific_success': False, 'graph_advantage_demonstrated': False,
        'policy_ru': 'Проверка привязки и полноты аннотации Codex, не экспертное подтверждение научного вывода. '
                     'Поддержка связывания мишени или доставки не означает эквивалентность генетического и '
                     'фармакологического воздействия. Неизвестные условия не заполняются; различия '
                     'режимов и противопоставления исходов сохраняются.'}

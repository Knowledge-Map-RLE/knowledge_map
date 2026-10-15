"""Скрининг контроля проверяет контекст до направления эффекта и не заменяет оценку."""
from collections import Counter
from datetime import date
from hashlib import sha256

from domain.article_maps import fingerprint, require

VERSION = 'source-bound-analogy-control-screen-1'
FIELDS = ('intervention', 'biological_system', 'challenge', 'route', 'assessment_hours')


def expected_context(hypothesis):
    p = hypothesis['proposed_protocol']
    return {'intervention': p['intervention']['identity'], 'biological_system': 'humanized_mouse',
        'challenge': p['challenge']['identity'], 'route': p['intervention']['route'],
        'assessment_hours': p['assessment_time']['proposed_hours_post_injection']}


def compare_context(expected, actual):
    require(set(expected) == set(actual) == set(FIELDS), 'Exact control context fields required')
    conflicts = [key for key in FIELDS if actual[key] is not None and actual[key] != expected[key]]
    unknown = [key for key in FIELDS if actual[key] is None]
    return {'status': 'incompatible_context' if conflicts else 'insufficient_information' if unknown else 'eligible_for_outcome_assessment',
            'conflicts': conflicts, 'unknown': unknown}


def screen_controls(forecast, registry, packets, annotation, training_forecast):
    require(forecast['question'] is None and forecast['model_calls'] == 0 and forecast['future_results_scored'] == 0,
            'Frozen source-only unscored forecast required')
    require(annotation['version'] == VERSION and annotation['author'] == 'Codex' and
            annotation['expert_validated'] is False and annotation['model_calls'] == 0, 'Explicit screening annotation required')
    require(annotation['forecast_sha256'] == fingerprint(forecast) and annotation['registry_sha256'] == fingerprint(registry),
            'Screening forecast or metadata changed')
    require(forecast['binding']['forecast_run_id'] == training_forecast['run_id'] and
            forecast['binding']['forecast_sha256'] == fingerprint(training_forecast), 'Original training forecast changed')
    require(registry['forecast_run_id'] == forecast['run_id'] and registry['forecast_sha256'] == fingerprint(forecast),
            'Search must follow this frozen forecast')
    cutoff = training_forecast['binding']['metadata']['training_cutoff']
    require(annotation['training_cutoff'] == cutoff, 'Control cutoff changed')
    records = {str(r['metadata']['source']) + ':' + str(r['metadata']['id']): r for r in registry['records']}
    require(len(records) == registry['record_count'] == len(registry['records']), 'Unique metadata record keys required')
    queries = {row['query'] for row in registry['queries'][:3]}
    eligible_records = {key for key, r in records.items() if set(r['queries']) & queries}
    rows = annotation['decisions']
    require(len(rows) == len(eligible_records) and {r['record_key'] for r in rows} == eligible_records,
            'Every specific later bibliographic hit must be screened')
    require(set(annotation['sources']) == set(packets), 'Exact full control packet registry required')
    for sid, packet in packets.items():
        source = packet['source']; binding = annotation['sources'][sid]
        require(packet['pmcid'] == sid and fingerprint(packet) == binding['packet_sha256'] and
                source['sha256'] == binding['source_sha256'] == sha256(source['text'].encode()).hexdigest(),
                'Full control packet identity or text changed')
        require(source['offset_encoding'] == 'unicode_codepoints' and type(source['content_end']) is int and
                0 < source['content_end'] <= len(source['text']), 'Control scientific source boundary required')
        require(len({u['id'] for u in source['units']}) == len(source['units']), 'Repeated control source unit')
        require(all(type(u['start']) is int and type(u['end']) is int and source['text'][u['start']:u['end']] == u['text'] and
                    0 <= u['start'] < u['end'] <= source['content_end'] for u in source['units']), 'Control Unicode units changed')
    decisions = []; comparisons = []
    for row in rows:
        meta = records[row['record_key']]['metadata']; types = set((meta.get('pubTypeList') or {}).get('pubType', []))
        published = meta['firstPublicationDate']
        require(date.fromisoformat(published).isoformat() == published and published > cutoff,
                'Control record does not follow training cutoff')
        require(row['reason_ru'], 'Screening reason required')
        status = row['status']
        if status == 'review_not_primary':
            require(bool(types & {'Review', 'review-article', 'Systematic Review'}), 'Review status not supported by metadata')
        elif status == 'abstract_not_full_primary':
            require(bool(types & {'Abstract', 'abstract', 'Meeting Report', 'meeting-report'}), 'Abstract status not supported')
        elif status == 'full_primary_context_screen':
            sid = meta['pmcid']; require(sid in packets, 'Bound full primary source required')
            require(packets[sid]['doi'] == meta['doi'], 'Control DOI identity differs')
            source = packets[sid]['source']; units = {u['id']: u for u in source['units']}
            require(row['evidence'] and row['contexts'], 'Explicit method contexts and evidence required')
            for e in row['evidence']:
                require(e['unit_id'] in units, 'Unknown control method unit')
                unit = units[e['unit_id']]
                require(e['start'] == unit['start'] and e['end'] == unit['end'] and e['text'] == unit['text'] and
                        e['sha256'] == sha256(unit['text'].encode()).hexdigest(), 'Control method evidence changed')
            for h in forecast['hypotheses']:
                for context in row['contexts']:
                    comparisons.append({'hypothesis_id': h['id'], 'record_key': row['record_key'],
                        'actual_context': context, **compare_context(expected_context(h), context)})
        elif status == 'full_xml_unavailable_partial_method_only':
            require(meta['pmcid'] not in packets and row['partial_evidence']['complete_full_source_bound'] is False and
                    row['partial_evidence']['url'] and row['partial_evidence']['text'], 'Partial source cannot masquerade as full control')
        else: require(False, 'Unknown control screening status')
        decisions.append(row)
    return {'version': VERSION, 'decisions': decisions, 'comparisons': comparisons,
        'metadata_records': len(records), 'specific_later_records': len(rows),
        'full_primary_controls_read': len(packets), 'decision_counts': dict(Counter(r['status'] for r in rows)),
        'comparison_counts': dict(Counter(r['status'] for r in comparisons)),
        'eligible_protocol_comparisons': sum(r['status'] == 'eligible_for_outcome_assessment' for r in comparisons),
        'future_directional_results_scored': 0, 'confirmed_predictions': 0, 'accuracy': None,
        'forecast_modified': False, 'scientific_success': False, 'graph_advantage_demonstrated': False,
        'model_calls': 0, 'expert_validated': False,
        'limits_ru': 'Ограниченный библиографический поиск, не доказательство отсутствия подходящих исследований. '
                     'Проверяется источниковая привязка аннотации Codex, не независимая экспертная интерпретация.'}

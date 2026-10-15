"""Первичный отсев контроля по явно описанной системе без чтения его исходов."""
from collections import Counter
from copy import deepcopy
from hashlib import sha256

from domain.article_maps import fingerprint, require

VERSION = 'source-bound-analogy-method-scope-screen-1'
DIMENSIONS = ('species', 'disease_model')
# Лексические признаки проверяют происхождение ручной лицензии, а не заменяют экспертизу.
LICENSES = {
    'mouse': ('species', ('mice', 'mouse')),
    'human': ('species', ('patients', 'children')),
    'mog_induced_eae_mouse_model': ('disease_model', ('mog', 'eae')),
    'moc2_perineural_invasion_mouse_model': ('disease_model', ('moc2', 'sciatic')),
    'juvenile_autoimmune_cross_sectional_human_study': ('disease_model', ('cross-sectional', 'jsle')),
    'acute_icv_amyloid_beta_oligomer_mouse_model': ('disease_model', ('intracerebroventricular', 'amyloid')),
}


def validate_packet(packet):
    source = packet['method_source']; text = source['text']
    require(packet['version'] == 'controlled-article-method-packet-2'
            and not packet['training_source'] and not packet['generator_access']
            and packet['model_calls'] == 0 and not packet['results_section_included'],
            'Isolated version-two method packet required')
    require(source['offset_encoding'] == 'unicode_codepoints'
            and source['coordinate_space'] == 'selected_method_text'
            and sha256(text.encode()).hexdigest() == source['sha256'], 'Method source changed')
    units = source['units']; require(len({u['id'] for u in units}) == len(units), 'Duplicate method unit')
    require(packet['has_explicit_methods'] == bool(packet['declared_method_sections'] and units), 'Method status differs')
    cursor = 0
    for index, unit in enumerate(units):
        if index: cursor += 2
        require(unit['start'] == cursor and unit['end'] == cursor + len(unit['text'])
                and text[unit['start']:unit['end']] == unit['text']
                and sha256(unit['text'].encode()).hexdigest() == unit['sha256']
                and any(unit['xpath'].startswith(s['xpath'] + '/') for s in packet['declared_method_sections']),
                'Method Unicode source or section path differs')
        cursor = unit['end']
    require(cursor == len(text) and '\n\n'.join(u['text'] for u in units) == text, 'Method packet is not exhaustive for its selected units')
    return {u['id']: u for u in units}


def screen_method_scope(protocol, packets, plan, annotation, disclosure):
    require(protocol['question'] is None and protocol['model_calls'] == 0
            and protocol['outside_budget_promoted'] is False, 'Frozen free-forecast protocol required')
    ids = protocol['eligible_draft_ids']
    require(len(set(ids)) == len(ids) and set(ids) <= set(protocol['fixed_original_slots'])
            and set(protocol['source_protocols']) == set(ids), 'Fixed draft budget differs')
    require(plan['protocol_sha256'] == fingerprint(protocol), 'Method acquisition registration differs')
    selected = {r['pmcid']: r for r in plan['selected']}
    require(len(selected) == len(plan['selected']) and set(packets) == set(selected), 'All selected controls must be accounted for')
    require(annotation['version'] == VERSION and annotation['author'] == 'Codex'
            and annotation['expert_validated'] is False and annotation['model_calls'] == 0
            and annotation['protocol_sha256'] == fingerprint(protocol)
            and annotation['method_plan_sha256'] == fingerprint(plan), 'Explicit source-bound scope annotation required')
    rows = {r['pmcid']: r for r in annotation['controls']}
    require(len(rows) == len(annotation['controls']) and set(rows) == set(selected), 'Control scope coverage differs')
    require(disclosure['model_calls'] == 0 and disclosure['forecasts_changed'] is False
            and disclosure['results_scored'] == 0, 'Disclosure cannot change or score the frozen forecast')
    disclosure_rows = {r['pmcid']: r for r in disclosure['controls']}
    require(len(disclosure_rows) == len(disclosure['controls']) and set(disclosure_rows) == set(selected), 'Disclosure coverage differs')
    for pmcid, packet in packets.items():
        require(packet['pmcid'] == pmcid and packet['doi'] == selected[pmcid]['doi'], 'Registered control identity differs')
        units = validate_packet(packet); row = rows[pmcid]
        require(row['packet_sha256'] == fingerprint(packet) and row['raw_xml_sha256'] == packet['raw_xml_sha256']
                and set(row['dimensions']) == set(DIMENSIONS) and row['shared_study_scope_only'] is True,
                'Method scope is not bound to the selected source')
        for dimension, fact in row['dimensions'].items():
            require(set(fact) == {'value', 'status', 'evidence', 'reason_ru'} and fact['reason_ru'], 'Explicit typed scope fact required')
            require(fact['status'] in {'codex_source_license', 'not_assessed'}, 'Unsupported context status')
            if fact['status'] == 'not_assessed':
                require(fact['value'] is None and fact['evidence'] == [], 'Unassessed scope cannot acquire a guessed value')
                continue
            require(packet['has_explicit_methods'] and fact['value'] in LICENSES and fact['evidence'], 'Grounded scope license required')
            licensed_dimension, cues = LICENSES[fact['value']]
            require(licensed_dimension == dimension, 'Context license has wrong type')
            quotes = []
            for ref in fact['evidence']:
                require(set(ref) == {'unit_id', 'unit_sha256', 'start', 'end', 'quote'} and ref['unit_id'] in units, 'Unknown method evidence')
                unit = units[ref['unit_id']]
                require(ref['unit_sha256'] == unit['sha256'] and ref['quote']
                        and isinstance(ref['start'], int) and isinstance(ref['end'], int)
                        and unit['start'] <= ref['start'] < ref['end'] <= unit['end']
                        and packet['method_source']['text'][ref['start']:ref['end']] == ref['quote'],
                        'Method quote or Unicode provenance differs')
                quotes.append(ref['quote'].casefold())
            # Два признака модели нужны вместе; для вида достаточно явного названия.
            joined = ' '.join(quotes)
            require((any(c in joined for c in cues) if dimension == 'species' else all(c in joined for c in cues)),
                    'Scope license is not supported by its literal source cues')
    comparisons = []; totals = Counter()
    for candidate_id in ids:
        designs = protocol['source_protocols'][candidate_id]
        require(bool(designs), 'Candidate has no registered design')
        for pmcid, row in rows.items():
            alternatives = []
            for design in designs:
                expected = {'species': design['population']['species'], 'disease_model': design['challenge']['id']}
                require(set(expected.values()) <= set(LICENSES), 'Explicit typed registered scope required')
                differences = []; unknowns = []
                for dim in DIMENSIONS:
                    actual = row['dimensions'][dim]
                    if actual['status'] == 'not_assessed': unknowns.append(dim)
                    elif expected[dim] != actual['value']:
                        differences.append({'dimension': dim, 'registered': expected[dim], 'control': actual['value'],
                                            'evidence': deepcopy(actual['evidence'])})
                status = ('incompatible_shared_study_scope' if differences else 'insufficient_shared_study_scope' if unknowns
                          else 'shared_scope_candidate_requires_full_protocol_audit')
                alternatives.append({'status': status, 'differences': differences, 'unknown_dimensions': unknowns,
                                     'registered_design_sha256': fingerprint(design), 'control_effect_scored': False})
            statuses = {a['status'] for a in alternatives}
            status = ('shared_scope_candidate_requires_full_protocol_audit' if 'shared_scope_candidate_requires_full_protocol_audit' in statuses
                      else 'insufficient_shared_study_scope' if 'insufficient_shared_study_scope' in statuses else 'incompatible_shared_study_scope')
            totals[status] += 1
            comparisons.append({'candidate_id': candidate_id, 'pmcid': pmcid, 'status': status, 'design_alternatives': alternatives,
                                'disclosure': deepcopy(disclosure_rows[pmcid]), 'control_effect_scored': False})
    return {'version': VERSION, 'question': None, 'controls': deepcopy(annotation['controls']), 'comparisons': comparisons,
            'counts': dict(totals), 'controls_accounted': len(rows), 'drafts_in_original_budget': len(ids),
            'original_slots': deepcopy(protocol['fixed_original_slots']), 'outside_budget_promoted': False,
            'method_plan': deepcopy(plan), 'context_annotation': deepcopy(annotation), 'disclosure_audit': deepcopy(disclosure),
            'model_calls': 0, 'future_results_scored': 0, 'new_confirmed_predictions': 0, 'accuracy': None,
            'scientific_success': False, 'graph_advantage_demonstrated': False, 'all_source_maps_rebuilt': False,
            'full_protocol_eligibility_established': False,
            'policy_ru': 'Проверены только общие вид и модель исследования. Одного явного несовпадения достаточно '
                         'для отказа; совпадение двух полей ещё не разрешает оценку эффекта. Неизученные дозы, '
                         'группы, способы введения, ткани, сроки и демография остаются обязательствами. '
                         'Неизвестность не является опровержением. Полнота поиска литературы и строгая слепота не заявляются.'}

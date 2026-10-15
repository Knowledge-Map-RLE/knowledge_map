"""Источниковые операции выполненной процедуры сохраняют полный родитель и контекст."""
from collections import Counter
from copy import deepcopy
from hashlib import sha256

from domain.article_maps import fingerprint, require
from domain.protocol_parameter_transfer import protocol_frame_identity

VERSION = 'source-bound-method-clause-projection-1'
GENERIC = {'perform experimental procedure', 'performed method'}
OPERATIONS = {
    'administer treatment', 'induce disease', 'measure clinical course', 'measure biomarkers',
    'measure drug levels', 'measure cognition', 'quantify transcripts', 'analyze data',
    'prepare intervention', 'collect biosample', 'prepare tissue', 'assess histology',
    'assess ultrastructure', 'measure barrier permeability', 'normalize measurements',
    'assess molecular structure', 'measure physical property', 'measure receptor binding',
}


def project_method_clauses(views, by_parent, known, maps, audit):
    require(audit.get('version') == VERSION and audit.get('author') == 'Codex'
            and audit.get('model_calls') == 0 and audit.get('expert_validated') is False,
            'Unsupported method clause provenance')
    sources = {m['article_id']: m for m in maps}
    require(len(sources) == len(maps), 'Repeated method source')
    for m in maps:
        require(m['source']['offset_encoding'] == 'unicode_codepoints'
                and sha256(m['source']['text'].encode('utf8')).hexdigest() == m['source']['sha256'],
                'Method source text or offset encoding differs')
    eligible = {k: v for k, v in views.items() if v['frame']['kind'] == 'action'
                and v['frame']['action_status'] == 'performed'
                and v['projection_proof']['origin']['origin'] == 'primary_method'}
    generic = {k: v for k, v in eligible.items() if v['frame']['statements'][0]['predicate'] in GENERIC}
    entries = {}
    for entry in audit['entries']:
        key = tuple(entry['part_key'])
        require(key in generic and key not in entries, 'Unknown or repeated generic procedure license')
        v = generic[key]; m = sources[v['native_key'][0]]; p = v['projection_proof']
        native = next((k for k in m['graph']['knowledge'] if k['knowledge_id'] == v['native_key'][1]), None)
        require(native is not None and native == p['complete_native_knowledge']
                and p['parent_key'] == list(v['native_key']) and p['run_id'] == v['run_id'],
                'Method parent differs from source map')
        require(entry['run_id'] == v['run_id'] == m['run_id'] and entry['source_sha256'] == m['source']['sha256']
                and entry['graph_sha256'] == fingerprint(m['graph'])
                and entry['view_frame_sha256'] == fingerprint(v['frame']) == p['view_frame_sha256']
                and entry['knowledge_sha256'] == fingerprint(p['complete_native_knowledge']),
                'Method license binding differs')
        s = v['frame']['statements'][0]
        require(not s['negated'] and s['scope']['modality'] is None,
                'Negated or modal procedure cannot supply performed clauses')
        require(entry['decision'] in {'source_asserted_clauses', 'retain_native'} and entry['reason_ru'],
                'Explicit method decision required')
        require(isinstance(entry['operations'], list), 'Method operations must be explicit')
        if entry['decision'] == 'retain_native':
            require(not entry['operations'], 'Retained native method cannot supply new clauses')
        else:
            require(entry['operations'] and len({op['predicate'] for op in entry['operations']}) == len(entry['operations']),
                    'Empty or duplicate method operations')
            units = {u['id']: u for u in m['source']['units']}
            parent_units = set(p['selected_provenance']['unit_ids'])
            for op in entry['operations']:
                e = op['evidence']
                require(op['predicate'] in OPERATIONS and op['source_asserts_performed_operation'] is True
                        and op['reason_ru'] and e['unit_id'] in parent_units, 'Unlicensed procedure operation')
                unit = units[e['unit_id']]
                require(unit['start'] <= e['start'] < e['end'] <= unit['end'] <= m['source']['content_end']
                        and e['text'] == m['source']['text'][e['start']:e['end']]
                        and e['sha256'] == sha256(e['text'].encode('utf8')).hexdigest(), 'Method clause evidence differs')
        entries[key] = entry
    require(set(entries) == set(generic), 'Every generic primary procedure needs a decision')
    result = deepcopy(views); registry = deepcopy(by_parent); existing = set(known)
    proofs, coverage, counts = [], [], Counter()
    for key, v in sorted(views.items()):
        if key not in eligible:
            counts['not_primary_performed_method'] += 1
            continue
        entry = entries.get(key)
        if entry is None:
            counts['specific_native_predicate_retained'] += 1
            coverage.append({'part_key': list(key), 'decision': 'specific_native_predicate_retained', 'new_views': []})
            continue
        created = []
        for op in entry['operations']:
            projected = deepcopy(v)
            projected['frame']['statements'][0]['predicate'] = op['predicate']
            # Все участники, числа и ограничения остаются неизменны; уточнение их областей требует отдельной лицензии.
            proof = deepcopy(projected['projection_proof'])
            proof.pop('id', None)
            clause = {'version': VERSION, 'audit_sha256': fingerprint(audit), 'entry_sha256': fingerprint(entry),
                'source_part_key': list(key), 'source_frame_sha256': fingerprint(v['frame']),
                'original_predicate': v['frame']['statements'][0]['predicate'], 'operation': deepcopy(op),
                'complete_parent_retained': True, 'participant_or_constraint_removed': False,
                'constraints_inherited_from_complete_parent_not_reassigned': True,
                'operation_is_complete_parent_equivalent': False, 'new_empirical_result': False,
                'expert_validated': False, 'statement_status': 'source_asserted_performed_method_clause'}
            clause['id'] = fingerprint(clause)
            proof['method_clause_proof'] = clause
            proof['operator'] = 'source_asserted_method_clause'
            proof['foundation'] = ('The linked source explicitly reports this performed operation. '
                'Codex supplies a source-bound clause interpretation; it is not an identity of the complete '
                'native predicate, a new measurement, an independent replication or a deductive empirical rule.')
            proof['view_frame_sha256'] = fingerprint(projected['frame'])
            proof['id'] = fingerprint(proof)
            projected['projection_proof'] = proof
            projected['key'] = (key[0], 'method-view:' + fingerprint({'parent_part': key, 'clause': clause['id']}))
            require(projected['key'] not in result, 'Repeated method view')
            result[projected['key']] = projected
            registry[v['native_key']].append(projected['key'])
            existing.add(protocol_frame_identity(projected['frame']))
            proofs.append(clause)
            created.append(list(projected['key']))
        counts[entry['decision']] += 1
        coverage.append({'part_key': list(key), 'decision': entry['decision'], 'new_views': created, 'reason_ru': entry['reason_ru']})
    return result, registry, existing, {'version': VERSION, 'audit_sha256': fingerprint(audit),
        'performed_actions_in_input': sum(v['frame']['kind'] == 'action' and v['frame']['action_status'] == 'performed' for v in views.values()),
        'primary_methods': len(eligible), 'generic_primary_methods': len(generic), 'counts': dict(counts),
        'coverage': coverage, 'proofs': proofs, 'added_views': len(proofs), 'model_calls': 0,
        'new_empirical_observations': 0, 'map_changed': False,
        'policy_ru': 'Исходные части сохраняются. Новые источниковые операции не являются независимыми репликациями '
                     'и не заменяют полный блок. Контексты, роли и числа не удалены; общий тип операции '
                     'не удостоверяет эквивалентность экспериментов или причинность.'}

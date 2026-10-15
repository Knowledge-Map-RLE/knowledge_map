"""Тождество и устранение конъюнкции сохраняют источник и полный исходный родитель."""
from collections import Counter
from copy import deepcopy

from domain.article_maps import fingerprint, require
from domain.compound_part_licenses import validate_licenses, FOUNDATION as CONTRAST_FOUNDATION, VERSION as CONTRAST_VERSION
from domain.protocol_parameter_transfer import protocol_frame_identity

VERSION = 'source-bound-semantic-part-projection-2'
FOUNDATION = {
    'identity': 'P entails P under the same declared scope and action status',
    'conjunction_elimination': 'P and Q entails P; source assertion, not an independent empirical replication',
}


def project_parts(records, originals, origin_index, compound_licenses=None):
    require(set(records) == set(originals), 'Complete native parent registry required')
    require(origin_index is not None and set(origin_index['knowledge']) == set(records), 'Complete source-origin registry required')
    licensed = validate_licenses(originals, origin_index, compound_licenses)
    views = {}; by_parent = {}; coverage = []; counts = Counter(); known = set()
    for key, record in sorted(records.items()):
        raw = originals[key]; frame = record['frame']; statements = frame['statements']
        require(key == record['key'] == raw['key'], 'Native parent identity differs')
        require(len(statements) == len(raw['frame']['statements']) == len(record['provenance']), 'Part projection changed source statement order')
        annotations = origin_index['knowledge'][key]['statements']
        require(len(annotations) == len(statements), 'Part origin coverage differs')
        native = raw.get('native_knowledge')
        require(native is not None and fingerprint(native) == origin_index['knowledge'][key]['knowledge_sha256'],
                'Exact native parent knowledge required')
        # Известность проверяется и по частям неподелённых аргументов: повтор не становится прогнозом.
        for source_frame in (frame, raw['frame']):
            for s in source_frame['statements']:
                known.add(protocol_frame_identity({**deepcopy(source_frame), 'logic': 'single', 'statements': [deepcopy(s)]}))
        reason = None
        if not record['eligible']: reason = 'unknown_parent_context'
        elif frame['logic'] not in {'single', 'conjunction'} and key not in licensed: reason = 'compound_requires_separate_operator_license'
        elif key in licensed and frame['logic'] != 'contrast': reason = 'licensed_parent_logic_changed'
        elif frame['logic'] == 'single' and len(statements) != 1: reason = 'invalid_single_statement_frame'
        elif not statements: reason = 'empty_parent'
        else:
            require(frame['kind'] in {'state', 'action'} and raw['frame']['kind'] == frame['kind']
                    and raw['frame']['action_status'] == frame['action_status'], 'Parent action status changed')
        keys = []
        if reason is None:
            for index, s in enumerate(statements):
                vid = 'part-view:' + fingerprint({'version': VERSION, 'parent': key, 'position': index})
                vkey = (key[0], vid)
                projected = {**deepcopy(frame), 'logic': 'single', 'statements': [deepcopy(s)]}
                operator = ('source_asserted_contrast_clause' if key in licensed else
                            'identity' if frame['logic'] == 'single' else 'conjunction_elimination')
                proof = {'version': VERSION, 'operator': operator,
                    'foundation': CONTRAST_FOUNDATION if key in licensed else FOUNDATION[operator],
                    'parent_key': list(key), 'run_id': record['run_id'], 'statement_position': index,
                    'native_statement_id': annotations[index]['statement_id'],
                    'parent_frame_sha256': fingerprint(raw['frame']), 'complete_parent_frame': deepcopy(raw['frame']),
                    'complete_native_knowledge': deepcopy(native), 'parent_knowledge_sha256': fingerprint(native),
                    'comparison_parent_frame': deepcopy(frame), 'view_frame_sha256': fingerprint(projected),
                    'complete_parent_provenance': deepcopy(record['provenance']),
                    'selected_provenance': deepcopy(record['provenance'][index]),
                    'origin': deepcopy(annotations[index]),
                    'numeric_proof_id': record.get('numeric_proof_id'),
                    'provenance_partition_proof_id': record.get('provenance_partition_proof_id'),
                    'source_locator_proof_id': record.get('source_locator_proof_id'),
                    'qualitative_result_proof_id': record.get('qualitative_result_proof_id'),
                    'conditions_removed': False, 'new_empirical_observation': False,
                    'independent_replication': False, 'causality_asserted': False}
                if key in licensed:
                    proof['compound_license'] = deepcopy(licensed[key])
                    proof['compound_license_version'] = CONTRAST_VERSION
                    proof['discourse_relation_retained'] = True
                    proof['clauses_are_independent_replications'] = False
                proof['id'] = fingerprint(proof)
                views[vkey] = {'key': vkey, 'frame': projected, 'run_id': record['run_id'],
                    'text': record['text'], 'eligible': True, 'provenance': [deepcopy(record['provenance'][index])],
                    'native_key': key, 'statement_position': index, 'projection_proof': proof}
                keys.append(vkey)
        by_parent[key] = keys
        counts[reason or 'licensed_parent'] += 1
        coverage.append({'article_id': key[0], 'knowledge_id': key[1], 'parent_logic': frame['logic'],
            'statement_count': len(statements), 'licensed_views': [list(v) for v in keys],
            'reason': reason, 'all_parent_constraints_retained': True,
            'new_knowledge_created': False})
    require(len(coverage) == len(records) and sum(len(v) for v in by_parent.values()) == len(views), 'Part coverage differs')
    summary = {'version': VERSION, 'foundation': FOUNDATION, 'coverage': coverage,
        'counts': dict(counts), 'canonical_blocks': len(records), 'licensed_view_count': len(views),
        'new_empirical_observations': 0, 'model_calls': 0}
    if compound_licenses is not None:
        summary['compound_licenses'] = {'version': CONTRAST_VERSION, 'audit_sha256': fingerprint(compound_licenses),
            'audited_parents': len(licensed), 'context_guard_overridden': False,
            'projected_parents': sum(bool(by_parent[key]) for key in licensed),
            'scope': 'explicit_source_bound_licenses_only'}
    return views, by_parent, known, summary

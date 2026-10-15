"""Идентификаторы происхождения отделяются от измерений с сохранением исходного фрейма."""
from copy import deepcopy
from domain.article_maps import fingerprint, require

VERSION = 'whole-map-provenance-partition-2'


def partition_provenance(records, families):
    projected, proofs = deepcopy(records), []
    for key, record in records.items():
        expected = {'study id': key[0], 'cohort id': families[key[0]], 'evidence family': families[key[0]]}
        separated = []
        for index, statement in enumerate(projected[key]['frame']['statements']):
            retained = []
            for attribute in statement['attributes']:
                if attribute['name'] not in expected:
                    retained.append(attribute)
                    continue
                require(attribute['value'] == expected[attribute['name']] and attribute['unit'] is None,
                        'Provenance identifier disagrees with explicit corpus identity')
                # Идентификатор публикации может быть служебной меткой утверждения без заданной группы участников.
                # Если научная область явно задана, она всё равно обязана совпадать с источником.
                require(statement['scope']['study_group'] in (None, key[0]),
                        'Source identity conflicts with the explicit study scope')
                require(not any(a['statement_index'] == index and a['attribute']['name'] == attribute['name'] for a in separated),
                        'Duplicate provenance identity')
                separated.append({'statement_index': index, 'attribute': deepcopy(attribute)})
            statement['attributes'] = retained
        if separated:
            proof = {'version': VERSION, 'key': key, 'run_id': record['run_id'],
                     'parent_frame': deepcopy(record['frame']), 'parent_frame_sha256': fingerprint(record['frame']),
                     'projected_frame_sha256': fingerprint(projected[key]['frame']), 'identifiers': separated,
                     'scientific_cohort_roles_and_scope_preserved': True,
                     'independent_evidence_certified': False}
            proof['id'] = fingerprint(proof)
            projected[key]['provenance_partition_proof_id'] = proof['id']
            proofs.append(proof)
    return projected, {'version': VERSION, 'proofs': proofs,
                       'policy': 'Only corpus-verified study/family identity attributes; quantities, species, evidence presentation, population roles and scientific scope remain',
                       'new_empirical_measurements': 0}

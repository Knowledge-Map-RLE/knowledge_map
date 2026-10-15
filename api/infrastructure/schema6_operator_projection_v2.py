"""Идентичность происхождения отдельно от научных ограничений оператора."""
from copy import deepcopy
from dataclasses import replace

from domain.article_maps import fingerprint
from infrastructure.schema6_operator_projection import project as project_v1

VERSION = 'schema6-operator-projection-2'
# Эти поля доказывают происхождение и независимость, а не клиническую применимость.
ORIGIN_ATTRIBUTES = frozenset({'study id', 'cohort id', 'sample id', 'evidence family'})
POLICY_SHA256 = fingerprint({'version': VERSION, 'origin_attributes': sorted(ORIGIN_ATTRIBUTES),
                            'retain': 'all predicates, roles, strata, scope, numeric attributes and evidence presentation'})


def project(result, family, published_on, annotations):
    projected = project_v1(result, family, published_on, annotations)
    records = []
    for item in projected['knowledge']:
        frame = deepcopy(item.frame)
        origins = []
        for statement in frame['statements']:
            metadata = [a for a in statement['attributes'] if a['name'] in ORIGIN_ATTRIBUTES]
            origins.append(metadata)
            statement['attributes'] = [a for a in statement['attributes'] if a['name'] not in ORIGIN_ATTRIBUTES]
        binding = deepcopy(item.binding)
        binding['frame_sha256'] = fingerprint(frame)
        # Первичная карта и её хеш сохранены; перенесённые метаданные не удаляются.
        for span in binding['provenance']:
            span['comparison_origin_metadata'] = origins
        record = replace(item, frame=frame, binding=binding)
        record.validate()
        records.append(record)
    return {**projected, 'knowledge': records,
            'binding': {**projected['binding'], 'projection_version': VERSION,
                        'origin_policy_sha256': POLICY_SHA256}}

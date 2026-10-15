"""Явно подготовленный корпус: результаты оценщика отделены от предпосылок."""
import json
from pathlib import Path
from domain.article_maps import require, fingerprint
from infrastructure.schema6_operator_projection import project


class PreparedOperatorCorpus:
    def __init__(self, catalog):
        self.catalog = dict(catalog)
        self.reads = []

    def _project(self, ref, stage='training'):
        require(ref in self.catalog, 'Unknown explicit operator source')
        row = self.catalog[ref]
        key = 'path' if stage == 'training' else stage + '_path'
        hash_key = 'sha256' if stage == 'training' else stage + '_sha256'
        raw = json.loads(Path(row[key]).read_text(encoding='utf-8'))
        require(fingerprint(raw) == row[hash_key], 'Prepared map changed')
        return project(raw['map'], raw['family'], raw['published_on'], raw['annotations'])

    def training(self, refs):
        self.reads.append({'stage': 'training', 'references': refs})
        rows = [self._project(r) for r in refs]
        return {'knowledge': [k for r in rows for k in r['knowledge']],
                'examples': [e for r in rows for e in r['examples']],
                'bindings': [r['binding'] for r in rows], 'rejected': [d for r in rows for d in r['rejected']]}

    def premises(self, ref):
        self.reads.append({'stage': 'premises', 'reference': ref})
        row = self._project(ref, 'premises')
        ids = self.catalog[ref]['premise_knowledge_ids']
        knowledge = [k for k in row['knowledge'] if k.binding['provenance'][0]['knowledge_id'] in ids]
        # В привязку прогноза не включён граф удержанных выводов.
        binding = {'reference': ref, 'article_id': row['binding']['article_id'],
                   'source_sha256': row['binding']['source_sha256'],
                   'knowledge_sha256': fingerprint([{'frame': k.frame, 'binding': k.binding,
                                                    'availability': k.availability, 'question_context': k.question_context} for k in knowledge]),
                   'knowledge_ids': ids, 'projection_version': row['binding']['projection_version'],
                   'normalizer_version': row['binding']['normalizer_version'],
                   'dictionary_sha256': row['binding']['dictionary_sha256']}
        return {'knowledge': knowledge, 'binding': binding}

    def outcomes(self, ref):
        self.reads.append({'stage': 'outcomes', 'reference': ref})
        row = self._project(ref, 'outcomes')
        ids = self.catalog[ref]['outcome_knowledge_ids']
        require(not set(ids) & set(self.catalog[ref]['premise_knowledge_ids']), 'Outcome leaked into application premises')
        knowledge = [k for k in row['knowledge'] if k.binding['provenance'][0]['knowledge_id'] in ids]
        return {'knowledge': knowledge, 'binding': {'source': row['binding'], 'outcome_ids': ids,
                                                   'premises_sha256': fingerprint(self.premises(ref)['binding'])}}

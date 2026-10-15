"""Явный экспериментальный корпус с проекцией 2; прежний корпус неизменен."""
import json
from pathlib import Path

from domain.article_maps import fingerprint, require
from infrastructure.prepared_operator_corpus import PreparedOperatorCorpus
from infrastructure.schema6_operator_projection_v2 import project


class ExpandedOperatorCorpus(PreparedOperatorCorpus):
    def _project(self, ref, stage='training'):
        require(ref in self.catalog, 'Unknown explicit expanded operator source')
        row = self.catalog[ref]
        key = 'path' if stage == 'training' else stage + '_path'
        hash_key = 'sha256' if stage == 'training' else stage + '_sha256'
        raw = json.loads(Path(row[key]).read_text(encoding='utf-8'))
        require(fingerprint(raw) == row[hash_key], 'Expanded map changed')
        return project(raw['map'], raw['family'], raw['published_on'], raw['annotations'])

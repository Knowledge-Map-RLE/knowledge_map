"""Чтение отдельного списка контрольных источников с проверкой байтовых хешей."""
import json
from hashlib import sha256
from pathlib import Path

from domain.article_maps import require


class FileMechanisticControls:
    def __init__(self, manifest):
        self.manifest = manifest
        self.reads = []

    def get(self, control_id):
        require(control_id in self.manifest, 'Control not explicitly listed')
        selected = self.manifest[control_id]
        result = []
        for kind in ('control', 'source'):
            item = selected[kind]; path = Path(item['path']).resolve(); raw = path.read_bytes()
            require(sha256(raw).hexdigest() == item['sha256'], 'Control artifact changed')
            self.reads.append({'kind': kind, 'path': str(path), 'sha256': item['sha256']})
            result.append(json.loads(raw))
        return tuple(result)

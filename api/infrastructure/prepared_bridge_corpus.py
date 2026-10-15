"""Явно разделённые контексты переноса и известные математические примеры."""
import hashlib
import json
from pathlib import Path
from domain.article_maps import require


class PreparedBridgeCorpus:
    def __init__(self, manifest):
        require(set(manifest) == {'contexts', 'mathematical_cases'}, 'Explicit bridge stage manifest required')
        self.manifest, self.reads = manifest, []

    def _read(self, name):
        entry = self.manifest[name]
        require(set(entry) == {'path', 'sha256'}, 'Exact file receipt required')
        data = Path(entry['path']).read_bytes()
        require(hashlib.sha256(data).hexdigest() == entry['sha256'], 'Bridge input changed')
        self.reads.append(name)
        return json.loads(data.decode('utf-8'))

    def contexts(self): return self._read('contexts')
    def mathematical_cases(self): return self._read('mathematical_cases')

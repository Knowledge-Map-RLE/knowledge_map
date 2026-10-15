"""Чтение только явно указанных файлов предпосылок, запросов и ответов."""
import json
import hashlib
from pathlib import Path
from domain.article_maps import require


class PreparedTransferCorpus:
    def __init__(self, manifest):
        require(set(manifest) == {'training', 'requests', 'outcomes'}, 'Explicit stage manifest required')
        self.manifest = manifest
        self.reads = []

    def _read(self, stage):
        entry = self.manifest[stage]
        require(set(entry) == {'path', 'sha256'}, 'Exact file binding required')
        content = Path(entry['path']).read_bytes()
        require(hashlib.sha256(content).hexdigest() == entry['sha256'], 'Prepared transfer file changed')
        result = json.loads(content.decode('utf-8'))
        self.reads.append(stage)
        return result

    def training(self): return self._read('training')
    def requests(self): return self._read('requests')
    def outcomes(self): return self._read('outcomes')

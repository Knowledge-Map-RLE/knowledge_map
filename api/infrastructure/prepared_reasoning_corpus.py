"""Физически разделённые предпосылки и контрольные ответы без AI-клиентов."""
import json
from pathlib import Path
from domain.article_maps import fingerprint,require

class PreparedReasoningCorpus:
    def __init__(self,manifest):self.manifest=manifest;self.reads=[]

    def _read(self,stage):
        entry=self.manifest[stage];raw=json.loads(Path(entry['path']).read_text(encoding='utf-8'))
        require(fingerprint(raw)==entry['sha256'],'Immutable reasoning input changed')
        self.reads.append(stage);return raw

    def premises(self):return self._read('premises')
    def controls(self):return self._read('controls')

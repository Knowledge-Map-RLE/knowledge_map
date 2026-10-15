"""Явно перечисленные локальные входы без общей базы, сети и AI-клиентов."""
import json
import re
from pathlib import Path
from domain.article_maps import fingerprint, require

class FileFoundationInputs:
    def __init__(self, path): self.path = Path(path).resolve(); self.reads = []
    def read(self, path):
        self.reads.append(str(path)); return json.loads(path.read_text(encoding='utf-8'))
    def read_inputs(self):
        manifest = self.read(self.path)
        require(manifest['protocol_sha256'] == fingerprint(manifest['protocol']), 'Protocol changed')
        require(manifest['protocol']['future_control_access'] is False and manifest['protocol']['model_calls'] == 0, 'Acquisition policy differs')
        require(manifest['foundation']['path'] == 'foundation.json', 'Foundation path differs')
        require(all(re.fullmatch(r'fold-[1-9][0-9]*\.json', i['path']) for i in manifest['folds']), 'Undeclared training fold path')
        def registered(item):
            path = (self.path.parent/item['path']).resolve()
            require(path.parent == self.path.parent and path.suffix == '.json', 'Undeclared input path')
            value = self.read(path); require(fingerprint(value) == item['sha256'], 'Registered input changed'); return value
        foundation = registered(manifest['foundation'])
        folds = [registered(item) for item in manifest['folds']]
        require(len({f['fold_id'] for f in folds}) == len(folds), 'Duplicate fold')
        return {'manifest': manifest, 'foundation': foundation, 'folds': folds}

class FileFoundationControls:
    def __init__(self, path): self.path = Path(path).resolve(); self.reads = []
    def read_controls(self):
        self.reads.append(str(self.path)); return json.loads(self.path.read_text(encoding='utf-8'))

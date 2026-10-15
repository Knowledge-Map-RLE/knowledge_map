"""Читает только перечисленные локальные материалы; не создаёт HTTP или AI клиентов."""
import json
from hashlib import sha256
from pathlib import Path

from domain.article_maps import fingerprint, require


class FileDefinitionAudit:
    def __init__(self, root):
        self.root=Path(root).resolve();self.reads=[]

    def read(self):
        manifest=json.loads((self.root/'inputs.json').read_text(encoding='utf-8'))
        self.reads.append(str(self.root/'inputs.json'))
        verified={}
        for name,expected in manifest['files'].items():
            path=(self.root/name).resolve()
            require(path.is_relative_to(self.root),'Input escapes audit root')
            require(not any(x in name for x in ['hidden-controls','future','control-metadata']),'Control input prohibited')
            raw=path.read_bytes();self.reads.append(str(path))
            require(sha256(raw).hexdigest()==expected,'Immutable input changed: '+name)
            verified[name]=raw
        selection=json.loads(verified['selection.json'])
        require(fingerprint(selection)==manifest['selection_sha256'] and selection['future_control_access'] is False,'Selection differs')
        require(all(e['role']=='training_candidate' for e in selection['entries']),'Nontraining source')
        return {'manifest':manifest,'spec':json.loads(verified['annotation-spec.json']),
                'evidence':json.loads(verified['source-evidence.json']),
                'texts':{'busse-bjp2003':verified['sources/busse-bjp2003/article.layout.txt'].decode('utf-8')},
                'repairs':json.loads(verified['quarantine-resolution.json']),
                'access':json.loads(verified['acquisition-status.json'])}

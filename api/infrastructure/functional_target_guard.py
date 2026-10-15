"""Явная цепочка сохранённых входов не расширяет корпус через общую базу."""
from hashlib import sha256
import json
from pathlib import Path
from domain.article_maps import fingerprint,require
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.measurement_orientation import load_sources


def load_functional_sources(root):
    root=Path(root).resolve();orientation=FilePredictionStore(root.parent).read_seal(root.name)
    require(orientation is not None,'Missing orientation seal')
    for f,d in orientation['binding']['implementation'].items():require(sha256((root/'implementation'/f).read_bytes()).hexdigest()==d,'Orientation implementation differs')
    p=json.loads((root/'input-corpus.json').read_bytes())
    previous,frozen,maps,origins,cases=load_sources(p['previous'],p['applicability'])
    require(fingerprint(previous)==orientation['binding']['previous_sha256'] and fingerprint(frozen)==orientation['binding']['source_sha256']
            and fingerprint(cases)==orientation['binding']['cases_sha256'],'Functional source chain differs')
    return orientation,frozen,maps,cases


class FileFunctionalInputs:
    def __init__(self,root,audit):self.root,self.audit=Path(root).resolve(),Path(audit).resolve()
    def load(self):return(*load_functional_sources(self.root),json.loads(self.audit.read_bytes()))

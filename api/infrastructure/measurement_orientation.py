"""Читает только явные сохранённые корпуса, проверяя повторную привязку случаев к источникам."""
import json
from hashlib import sha256
from pathlib import Path
from domain.article_maps import fingerprint,require
from domain.operation_applicability import analyze
from infrastructure.interval_knowledge import FileIntervalInputs
from infrastructure.development_prediction_store import FilePredictionStore


def load_sources(root,applicability):
    root,applicability=Path(root).resolve(),Path(applicability).resolve()
    previous=FilePredictionStore(root.parent).read_seal(root.name)
    require(previous is not None,'Missing interval forecast')
    for f,d in previous['binding']['implementation'].items():require(sha256((root/'implementation'/f).read_bytes()).hexdigest()==d,'Interval implementation differs')
    pointer=json.loads((root/'input-corpus.json').read_bytes())
    baseline,frozen,maps,origins,_=FileIntervalInputs(pointer['baseline'],root/'audit.json').load()
    require(fingerprint(baseline)==previous['binding']['baseline_sha256'] and fingerprint(frozen)==previous['binding']['source_sha256'],
            'Orientation interval corpus differs')
    contract=FilePredictionStore(applicability.parent).read_seal(applicability.name)
    require(contract is not None and contract['binding']['input_sha256']==fingerprint(frozen),'Orientation case corpus differs')
    for f,d in contract['binding']['implementation'].items():require(sha256((applicability/'implementation'/f).read_bytes()).hexdigest()==d,'Case implementation differs')
    audit=json.loads((applicability/'audit.json').read_bytes());require(fingerprint(audit)==contract['binding']['audit_sha256'],'Case audit differs')
    replay=analyze(frozen,maps,origins,audit)
    require(all(contract[k]==v for k,v in replay.items()),'Case source replay differs')
    return previous,frozen,maps,origins,contract['cases']


class FileOrientationInputs:
    def __init__(self,root,applicability,audit):
        self.root,self.applicability,self.audit=Path(root).resolve(),Path(applicability).resolve(),Path(audit).resolve()

    def load(self):return (*load_sources(self.root,self.applicability),json.loads(self.audit.read_bytes()))

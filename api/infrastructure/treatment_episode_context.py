"""Чтение явных снимков и сохранённого рисунка, без новых сетевых обращений."""
from hashlib import sha256
import json
from pathlib import Path
from domain.article_maps import fingerprint,require
from domain.functional_target_guard import compile_guards
from infrastructure.functional_target_guard import load_functional_sources
from infrastructure.development_prediction_store import FilePredictionStore


def load_episode_sources(root):
    root=Path(root).resolve();functional=FilePredictionStore(root.parent).read_seal(root.name)
    require(functional is not None,'Missing functional seal')
    for f,d in functional['binding']['implementation'].items():
        require(sha256((root/'implementation'/f).read_bytes()).hexdigest()==d,'Functional implementation changed')
    pointer=json.loads((root/'input-corpus.json').read_bytes())
    orientation,frozen,maps,cases=load_functional_sources(pointer['orientation'])
    audit=json.loads((root/'audit.json').read_bytes())
    require(fingerprint(orientation)==functional['binding']['orientation_sha256']
        and fingerprint(audit)==functional['binding']['audit_sha256'],'Functional input binding changed')
    require(all(functional[k]==v for k,v in compile_guards(orientation,frozen,maps,cases,audit).items()),'Functional replay differs')
    return functional,frozen,maps,cases


class FileEpisodeInputs:
    def __init__(self,root,audit):self.root,self.audit=Path(root).resolve(),Path(audit).resolve()

    def load(self):
        data=json.loads(self.audit.read_bytes());assets={}
        for key,e in data['assets'].items():
            relative=Path(e['path']);require(not relative.is_absolute(),'Episode asset path must be relative')
            path=(self.audit.parent/relative).resolve();require(path.is_relative_to(self.audit.parent),'Episode asset escapes its snapshot')
            assets[key]=path.read_bytes()
        return(*load_episode_sources(self.root),data,assets)

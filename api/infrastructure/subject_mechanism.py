"""Файловые входы, точные координаты и независимое чтение профилей."""
import json
from pathlib import Path
from domain.article_maps import fingerprint, digest, require

class FileMechanismInputs:
    def __init__(self,path): self.path=Path(path).resolve();self.reads=[]
    def read(self,path):
        self.reads.append(str(path));return json.loads(path.read_text(encoding='utf-8'))
    def read_inputs(self):
        manifest=self.read(self.path)
        def registered(item):
            path=(self.path.parent/item['path']).resolve()
            require(path.parent==self.path.parent and path.suffix=='.json','Undeclared input path')
            value=self.read(path);require(fingerprint(value)==item['sha256'],'Input changed');return value
        inputs=registered(manifest['inputs']); evidence=registered(manifest['evidence'])
        require(fingerprint(evidence)==inputs['protocol']['evidence_sha256'],'Input source binding changed')
        require(inputs['protocol']['registered_evidence_ids']==sorted(evidence['fragments']),'Registered evidence differs')
        foundation_path=Path(inputs['foundation_binding']['path']).resolve()
        require(foundation_path==self.path.parents[2]/'foundation-pilot-v1/prepared/foundation.json','Unexpected foundation path')
        foundation=self.read(foundation_path)
        require(fingerprint(foundation)==inputs['foundation_binding']['sha256'],'Foundation changed')
        for item in evidence['fragments'].values():
            source=evidence['sources'][item['source_id']]
            path=Path(source['path']);self.reads.append(str(path))
            text=path.read_text(encoding='utf-8')
            require(digest(text)==source['sha256'],'Source changed')
            require(type(item['start']) is int and type(item['end']) is int and 0<=item['start']<item['end']<=len(text),'Invalid source offsets')
            fragment=text[item['start']:item['end']]
            require(fragment==item['text'] and digest(fragment)==item['text_sha256'],'Source fragment changed')
        for block in inputs['knowledge']:
            require(all(p in evidence['fragments'] or p in evidence['authored_sources'] for p in block['provenance']),'Unknown provenance')
        return inputs

class FileMechanismProfiles:
    def __init__(self,path):self.path=Path(path).resolve();self.reads=[]
    def read_profiles(self):
        self.reads.append(str(self.path));return json.loads(self.path.read_text(encoding='utf-8'))

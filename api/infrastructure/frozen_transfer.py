"""Адресные старые знания; контролы, сеть и Neo4j не читаются."""
import json
from pathlib import Path
from domain.article_maps import fingerprint,digest,require

class FileTransferInputs:
    def __init__(self,path):self.path=Path(path).resolve();self.reads=[]
    def read(self,path):self.reads.append(str(path));return json.loads(path.read_text(encoding='utf-8'))
    def read_inputs(self):
        manifest=self.read(self.path);data={}
        for key in ['protocol','annotation','foundation']:
            entry=manifest[key];path=Path(entry['path']).resolve()
            require(path.suffix=='.json','JSON input required');value=self.read(path)
            require(fingerprint(value)==entry['sha256'],'Frozen input changed');data[key]=value
        require(data['protocol']['training_source_ids']==sorted(data['annotation']['sources']),'Source corpus differs')
        for source,meta in data['annotation']['sources'].items():
            path=Path(meta['path']);self.reads.append(str(path));text=path.read_text(encoding='utf-8')
            require(digest(text)==meta['sha256'],'Source text changed')
            for f in data['annotation']['evidence'].values():
                if f['source_id']!=source:continue
                require(0<=f['start']<f['end']<=len(text) and text[f['start']:f['end']]==f['text'] and digest(f['text'])==f['text_sha256'],'Unicode provenance differs')
        return data

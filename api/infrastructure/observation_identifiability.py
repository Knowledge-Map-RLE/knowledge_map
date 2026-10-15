"""Адресные файловые источники и атомарный маркер завершения аудита."""
import json
import re
from pathlib import Path
from domain.article_maps import digest,fingerprint,require
from infrastructure.immutable_files import write_immutable

class FileObservationInputs:
    def __init__(self,path):self.path=Path(path).resolve();self.reads=[]
    def read_json(self,path):
        self.reads.append(str(path));return json.loads(path.read_text(encoding='utf-8'))
    def read_inputs(self):
        manifest=self.read_json(self.path);values={}
        for key in ['catalog','evidence']:
            entry=manifest[key];path=(self.path.parent/entry['path']).resolve()
            require(path.parent==self.path.parent and path.suffix=='.json','Unregistered input path')
            values[key]=self.read_json(path)
            require(fingerprint(values[key])==entry['sha256'],'Registered input changed')
        evidence=values['evidence'];catalog=values['catalog']
        require({s['source_id'] for s in catalog['sources']}==set(evidence['sources']) and len(catalog['sources'])==len(evidence['sources']),'Corpus membership differs')
        require(catalog['evidence_sha256']==fingerprint(evidence),'Evidence binding differs')
        for identifier,meta in evidence['sources'].items():
            path=Path(meta['path']);self.reads.append(str(path));text=path.read_text(encoding='utf-8')
            require(digest(text)==meta['sha256'],'Full source changed')
            for f in evidence['fragments'].values():
                if f['source_id']!=identifier:continue
                require(type(f['start']) is int and type(f['end']) is int and 0<=f['start']<f['end']<=len(text),'Invalid Unicode coordinates')
                require(text[f['start']:f['end']]==f['text'] and digest(f['text'])==f['sha256'],'Fragment changed')
        references=[p for s in catalog['sources'] for p in s['provenance']]+catalog['paquid_table']['provenance']
        require(set(references)<=set(evidence['fragments']),'Unknown source fragment')
        prior=Path(catalog['prior_result']['path']).resolve();value=self.read_json(prior)
        require(fingerprint(value)==catalog['prior_result']['sha256'],'Prior result changed')
        return values

class FileObservationAuditStore:
    def __init__(self,root):self.root=Path(root).resolve()
    def path(self,run_id):
        require(bool(re.fullmatch('[a-f0-9]{64}',run_id)),'Invalid audit id')
        return self.root/run_id
    @staticmethod
    def encode(value):return (json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n').encode('utf-8')
    def read(self,run_id):
        folder=self.path(run_id)
        if not (folder/'seal.json').exists():return None
        seal=json.loads((folder/'seal.json').read_text(encoding='utf-8'))
        value=json.loads((folder/'audit.json').read_text(encoding='utf-8'))
        require(value['run_id']==run_id and fingerprint(value)==seal['audit_sha256'],'Audit seal changed')
        return value
    def save(self,run_id,result):
        require(result['run_id']==run_id,'Audit id differs')
        folder=self.path(run_id)
        write_immutable(folder/'audit.json',self.encode(result))
        write_immutable(folder/'seal.json',self.encode({'run_id':run_id,'audit_sha256':fingerprint(result)}))

"""Файловые неизменяемые артефакты изолированного опыта."""
import json
from pathlib import Path
from domain.article_maps import require, parse_json_response
from infrastructure.immutable_files import write_immutable

class FileEmpiricalForecastStore:
    def __init__(self, root): self.root=Path(root)

    @staticmethod
    def encode(raw): return (json.dumps(raw,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n').encode('utf-8')

    @staticmethod
    def identity(value):
        require(isinstance(value,str) and len(value)==64 and all(c in '0123456789abcdef' for c in value),'Invalid immutable artifact identity')
        return value

    def seal(self,run_id,artifact):
        write_immutable(self.root/self.identity(run_id)/'sealed.json',self.encode(artifact))

    def read_seal(self,run_id):
        return parse_json_response((self.root/self.identity(run_id)/'sealed.json').read_text(encoding='utf-8'))

    def evaluate(self,run_id,evaluation_id,artifact):
        write_immutable(self.root/self.identity(run_id)/'evaluations'/f'{self.identity(evaluation_id)}.json',self.encode(artifact))

class PreparedEmpiricalCorpus:
    def __init__(self,observations):
        require(len({o.reference for o in observations})==len(observations),'Duplicate corpus reference')
        self.observations={o.reference:o for o in observations};self.reads=[]

    def read(self,references):
        require(len(references)==len(set(references)) and all(r in self.observations for r in references),'Unknown or duplicated explicit source')
        self.reads.extend(references)
        return [self.observations[r] for r in references]

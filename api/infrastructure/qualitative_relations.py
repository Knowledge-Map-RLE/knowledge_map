"""Локальные порты не создают AI-клиентов и не расширяют обучающий корпус."""
import json
from pathlib import Path
from domain.article_maps import fingerprint,require

class FileQualitativeInputs:
    def __init__(self,manifest):self.path=Path(manifest).resolve();self.reads=[]
    def read_inputs(self):
        self.reads.append(str(self.path));manifest=json.loads(self.path.read_text(encoding='utf-8'))
        require(manifest['protocol']['future_control_access'] is False and manifest['protocol']['model_calls']==0,'Invalid acquisition policy')
        require(manifest['protocol_sha256']==fingerprint(manifest['protocol']),'Protocol changed')
        folds=[]
        for item in manifest['folds']:
            path=(self.path.parent/item['path']).resolve()
            require(path.parent==self.path.parent and path.name.startswith('fold-') and path.suffix=='.json','Undeclared input path')
            self.reads.append(str(path));fold=json.loads(path.read_text(encoding='utf-8'))
            require(fingerprint(fold)==item['sha256'],'Fold changed');folds.append(fold)
        require(len({f['fold_id'] for f in folds})==len(folds),'Duplicate fold')
        return {'manifest':manifest,'folds':folds}

class FileQualitativeControls:
    def __init__(self,path):self.path=Path(path).resolve();self.reads=[]
    def read_controls(self):
        self.reads.append(str(self.path));return json.loads(self.path.read_text(encoding='utf-8'))

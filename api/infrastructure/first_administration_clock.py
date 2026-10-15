"""Явное чтение временного снимка с повторной сверкой источников и изображения."""
from hashlib import sha256
import json
from pathlib import Path
from domain.article_maps import require
from domain.treatment_episode_context import compile_episodes
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.treatment_episode_context import FileEpisodeInputs


class FileClockInputs:
    def __init__(self,root):self.root=Path(root).resolve()

    def load(self):
        source=FilePredictionStore(self.root.parent).read_seal(self.root.name);require(source is not None,'Missing episode seal')
        for f,d in source['binding']['implementation'].items():
            require(sha256((self.root/'implementation'/f).read_bytes()).hexdigest()==d,'Episode implementation changed')
        descriptor=json.loads((self.root/'input-corpus.json').read_bytes())
        data=FileEpisodeInputs(descriptor['functional'],self.root/'audit.json').load()
        require(all(source[k]==v for k,v in compile_episodes(*data).items()),'Episode source replay changed')
        return source

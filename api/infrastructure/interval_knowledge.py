"""Загружает только явно перечисленные печати и полный сохранённый корпус."""
import json
from hashlib import sha256
from pathlib import Path
from domain.article_maps import fingerprint, require
from infrastructure.sealed_forecast_corpus import SealedForecastCorpus
from infrastructure.development_prediction_store import FilePredictionStore


class FileIntervalInputs:
    def __init__(self, root, audit):
        self.root, self.audit = Path(root).resolve(), Path(audit).resolve()

    def load(self):
        baseline = FilePredictionStore(self.root.parent).read_seal(self.root.name)
        require(baseline is not None, 'Missing typed participant baseline')
        for file, digest in baseline['binding']['implementation'].items():
            require(sha256((self.root / 'implementation' / file).read_bytes()).hexdigest() == digest, 'Baseline implementation snapshot differs')
        source = json.loads((self.root / 'input-corpus.json').read_bytes())
        frozen, maps, origins = SealedForecastCorpus(source['snapshot']).load()
        require(fingerprint(frozen) == baseline['binding']['source_sha256'], 'Interval upstream differs')
        return baseline, frozen, maps, origins, json.loads(self.audit.read_bytes())

"""Читает только явный запечатанный корпус, проверяя версии и происхождение."""
import json
from hashlib import sha256
from pathlib import Path

from domain.article_maps import fingerprint, require
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.free_prediction_snapshots import FileForecastMaps


class SealedForecastCorpus:
    def __init__(self, root):
        self.root = Path(root).resolve()

    def read(self, relative):
        path = (self.root / relative).resolve()
        require(path.is_relative_to(self.root), 'Corpus path escapes snapshot')
        return path.read_bytes()

    def load(self):
        forecast = FilePredictionStore(self.root.parent).read_seal(self.root.name)
        require(forecast is not None and forecast['run_id'] == self.root.name, 'Missing forecast seal')
        ix = json.loads(self.read('inputs-manifest.json')); manifest = json.loads(self.read('source-manifest.json'))
        require(ix['target_read'] is False and ix['model_calls'] == 0, 'Snapshot used models or target')
        require([e['reference'] for e in ix['sources']] == forecast['binding']['references'], 'Corpus references differ')
        require(len(ix['sources']) == len(manifest['sources']) == len(forecast['binding']['map_hashes']), 'Corpus count differs')
        entries = []
        for e, original in zip(ix['sources'], manifest['sources']):
            require(e['reference'] == original['reference'], 'Corpus manifest identity differs')
            require(sha256(self.read(e['map_path'])).hexdigest() == e['map_file_sha256'], 'Map bytes differ')
            row = {**original, 'path': str((self.root / e['map_path']).resolve())}
            if 'coverage_path' in e:
                require(sha256(self.read(e['coverage_path'])).hexdigest() == e['coverage_sha256'], 'Coverage bytes differ')
                row['coverage_artifact'] = {'path': str((self.root / e['coverage_path']).resolve()), 'sha256': e['coverage_sha256']}
            entries.append(row)
        port = FileForecastMaps(entries); maps = []
        for e, expected in zip(entries, forecast['binding']['map_hashes']):
            r = e['reference']; m = port.get(r['article_id'], r['pipeline_id'], port.owner, r['run_id'])
            require(fingerprint(m) == expected, 'Bound input map differs')
            require(m['source']['sha256'] != 'f7df96ff746be4a60a6930ff2c5c25435725d0591dfe1f492259624b2d7c0bc8', 'Approved target is excluded')
            maps.append(m)
        for name, digest in forecast['binding']['implementation'].items():
            require(sha256(self.read('implementation/' + name)).hexdigest() == digest, 'Snapshot implementation differs')
        raw = self.read('origin-audit.json')
        require(sha256(raw).hexdigest() == forecast['binding']['metadata']['input_audit_file_sha256']['origin-audit'], 'Origin audit bytes differ')
        return forecast, maps, json.loads(raw)

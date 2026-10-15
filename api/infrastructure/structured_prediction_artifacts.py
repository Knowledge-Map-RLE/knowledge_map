"""Файловые неизменяемые результаты экспериментальных прогнозов без AI-клиентов."""
import json
import re
from pathlib import Path
from domain.article_maps import require, parse_json_response
from infrastructure.immutable_files import write_immutable

class FileStructuredForecastArtifacts:
    def __init__(self, root): self.root = Path(root).resolve()

    def path(self, identifier):
        require(isinstance(identifier, str) and bool(re.fullmatch('[a-f0-9]{64}', identifier)), 'Invalid artifact identity')
        return self.root / identifier

    def write(self, path, value):
        write_immutable(path, (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode())

    def seal(self, run_id, value): self.write(self.path(run_id) / 'prediction.json', value)

    def read_seal(self, run_id): return parse_json_response((self.path(run_id) / 'prediction.json').read_text(encoding='utf-8'))

    def evaluate(self, run_id, evaluation_id, value):
        self.read_seal(run_id)
        require(bool(re.fullmatch('[a-f0-9]{64}', evaluation_id)), 'Invalid evaluation identity')
        self.write(self.path(run_id) / 'evaluations' / (evaluation_id + '.json'), value)

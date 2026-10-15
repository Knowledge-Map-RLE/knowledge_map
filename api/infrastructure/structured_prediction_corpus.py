"""Явный файловый корпус: прогноз не читает исходы удержанной семьи."""
import hashlib
from pathlib import Path
from domain.article_maps import require, parse_json_response
from domain.structured_question_forecast import validate_request, validate_observation

class ExplicitStructuredFiles:
    def __init__(self, root):
        self.root = Path(root).resolve()
        data = parse_json_response((self.root / 'index.json').read_text(encoding='utf-8'))
        require(isinstance(data, list) and data and len({row['reference'] for row in data}) == len(data), 'Unique explicit corpus required')
        self.index = {row['reference']: row for row in data}
        self.reads = []

    def read(self, reference, kind):
        require(reference in self.index and kind in {'context', 'observation'}, 'Unknown explicit source')
        entry = self.index[reference]
        path = (self.root / entry[kind + '_path']).resolve()
        require(path.is_relative_to(self.root), 'Corpus path escapes explicit root')
        raw = path.read_bytes()
        require(hashlib.sha256(raw).hexdigest() == entry[kind + '_sha256'], 'Prepared corpus file changed')
        value = parse_json_response(raw.decode('utf-8'))
        require(all(value[key] == entry[key] for key in ('reference', 'family', 'available_on')), 'Corpus identity differs from explicit index')
        self.reads.append({'reference': reference, 'kind': kind})
        return value

class PreparedStructuredTrainingCorpus(ExplicitStructuredFiles):
    def context(self, reference):
        value = self.read(reference, 'context'); validate_request(value)
        return value

    def earlier_other_families(self, family, before):
        selected = [row for row in self.index.values() if row['family'] != family and row['available_on'] < before]
        results = []
        for row in sorted(selected, key=lambda r: r['reference']):
            value = self.read(row['reference'], 'observation'); validate_observation(value)
            results.append(value)
        return results

class PreparedStructuredTargetOutcomes(ExplicitStructuredFiles):
    def outcome(self, reference):
        value = self.read(reference, 'observation'); validate_observation(value)
        return value

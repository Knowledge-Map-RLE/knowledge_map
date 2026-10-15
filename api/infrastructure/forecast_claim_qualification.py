"""Порт читает полный явный корпус и источниковый аудит после фиксации кандидатов."""
from hashlib import sha256
import json
from pathlib import Path

from domain.article_maps import fingerprint, require
from domain.forecast_temporal_scope import validate_contract
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.external_operation_inputs import read_bound_source, validate_evidence
from infrastructure.sealed_forecast_corpus import SealedForecastCorpus


class FileClaimQualificationInputs:
    def __init__(self, forecast_root, audit_path):
        self.root, self.audit_path = Path(forecast_root).resolve(), Path(audit_path).resolve()

    def load(self):
        frozen = FilePredictionStore(self.root.parent).read_seal(self.root.name)
        require(frozen is not None, 'Frozen forecast required before qualification')
        for name, digest in frozen['binding']['implementation'].items():
            require(sha256((self.root / 'implementation' / name).read_bytes()).hexdigest() == digest, 'Forecast implementation differs')
        descriptor = json.loads((self.root / 'input-corpus.json').read_bytes())
        applicability_root = Path(descriptor['snapshot'])
        applicability = FilePredictionStore(applicability_root.parent).read_seal(applicability_root.name)
        require(fingerprint(applicability) == frozen['binding']['input_sha256'], 'Frozen training binding differs')
        upstream_root = Path(json.loads((applicability_root / 'input-corpus.json').read_bytes())['snapshot'])
        upstream, maps, _ = SealedForecastCorpus(upstream_root).load()
        require(fingerprint(upstream) == applicability['binding']['input_sha256'], 'Qualification upstream differs')
        audit = json.loads(self.audit_path.read_bytes())
        source = read_bound_source(self.root / 'external-source.json')
        require(audit['external_source_packet_sha256'] == fingerprint(source) and audit['external_doi'] == source['doi'], 'Temporal source binding differs')
        require([fingerprint(m) for m in maps] == audit['map_hashes'], 'Qualification complete corpus changed')
        for row in audit['candidates']:
            for observed in row['outcome_temporal_observations']:
                validate_contract(observed['contract'])
                for e in observed['evidence']: validate_evidence(source['source'], e)
        return frozen, maps, audit

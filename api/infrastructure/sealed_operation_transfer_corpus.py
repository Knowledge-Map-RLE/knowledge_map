"""Повторно проверяет контракт и формирует отдельные входы генератора и оценщика."""
import json
from copy import deepcopy
from pathlib import Path

from domain.article_maps import fingerprint, require
from domain.comparison_normalization import normalize_map
from domain.conditional_operation_transfer import receiver_from_case
from domain.operation_applicability import analyze
from infrastructure.development_prediction_store import FilePredictionStore
from infrastructure.sealed_forecast_corpus import SealedForecastCorpus


class SealedOperationTransferCorpus:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self._outcomes = None

    def load(self):
        sealed = FilePredictionStore(self.root.parent).read_seal(self.root.name)
        require(sealed is not None, 'Missing applicability seal')
        descriptor = json.loads((self.root / 'input-corpus.json').read_bytes())
        corpus = SealedForecastCorpus(descriptor['snapshot'])
        forecast, maps, origins = corpus.load()
        require(fingerprint(forecast) == sealed['binding']['input_sha256'], 'Applicability upstream differs')
        audit = json.loads((self.root / 'audit.json').read_bytes())
        require(fingerprint(audit) == sealed['binding']['audit_sha256'], 'Applicability audit differs')
        for name, digest in sealed['binding']['implementation'].items():
            from hashlib import sha256
            require(sha256((self.root / 'implementation' / name).read_bytes()).hexdigest() == digest,
                    'Applicability implementation snapshot differs')
        replay = analyze(forecast, maps, origins, audit)
        require(all(sealed[key] == value for key, value in replay.items()), 'Applicability replay differs')
        groups = set()
        for m in maps:
            for k in normalize_map(m):
                groups.update((tuple(sorted((m['article_id'], p) for p in group)), (m['article_id'], k['id']))
                              for group in k['premise_groups'])
        cases = sealed['cases']
        self._outcomes = {c['case_id']: {k: deepcopy(c[k]) for k in
                          ('qualitative_direction', 'outcome_class', 'predicate', 'result', 'source_annotation')}
                          for c in cases}
        return {'input_run_id': sealed['run_id'], 'input_sha256': fingerprint(sealed),
                'cases': deepcopy(cases), 'receivers': [receiver_from_case(c) for c in cases],
                'author_groups': [[list(body), list(head)] for body, head in sorted(groups)],
                'coverage': {'canonical_blocks': sealed['canonical_blocks'], 'licensed_parts': sealed['licensed_parts'],
                             'sources': len(maps), **deepcopy(sealed['coverage'])}}

    def outcomes(self):
        require(self._outcomes is not None, 'Load transfer corpus before evaluation')
        return deepcopy(self._outcomes)

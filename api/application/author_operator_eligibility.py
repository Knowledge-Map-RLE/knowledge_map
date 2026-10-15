"""Неизменяемый аудит перед обучением не изменяет карты или прежние прогнозы."""
from application.ports.development_prediction import PredictionStore
from domain.article_maps import require, fingerprint, ArticleMapNotFound
from domain.author_operator_eligibility import audit_author_operators, VERSION


class AuditSealedAuthorOperators:
    def __init__(self, sources: PredictionStore, output: PredictionStore): self.sources, self.output = sources, output

    def execute(self, source_run, previous_max_premises, implementation):
        source = self.sources.read_seal(source_run)
        if source is None: raise ArticleMapNotFound('Explicit full argument source missing')
        require(fingerprint(source['binding']) == source_run, 'Full argument binding changed')
        excluded = set(source['binding']['metadata']['excluded_source_sha256'])
        require(excluded and not (excluded & {p['source_sha256'] for p in source['semantic_graph']['parents'].values()}),
                'Excluded target in operator training source')
        binding = {'version': VERSION, 'source_run_id': source_run, 'source_artifact_sha256': fingerprint(source),
                   'previous_max_premises': previous_max_premises, 'implementation': implementation}
        result = audit_author_operators(source, previous_max_premises); run = fingerprint(binding)
        self.output.seal(run, {'run_id': run, 'binding': binding, **result})
        return self.output.read_seal(run)

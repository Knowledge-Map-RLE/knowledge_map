"""Полный явный корпус и неизменяемый прогноз частей проверяются до публикации."""
import logging
from datetime import date
from time import perf_counter

from application.compare_article_maps import validate_reference
from application.ports.article_comparisons import ComparisonMaps
from application.ports.development_prediction import PredictionStore
from domain.article_maps import fingerprint, require, ArticleMapNotFound
from domain.semantic_part_forecast import forecast_parts, VERSION, LIMITS
from domain.whole_map_input_audit import audit_corpus

log = logging.getLogger(__name__)


class SealSemanticPartForecast:
    def __init__(self, maps: ComparisonMaps, store: PredictionStore):
        self.maps, self.store = maps, store

    def execute(self, references, families, owner, metadata, implementation, context_audit, model_audit, origin_audit, compound_licenses=None, method_clauses=None, role_bindings=None):
        started = perf_counter()
        require(len(references) >= 2 and len({r['article_id'] for r in references}) == len(references), 'Explicit distinct part source maps required')
        require(metadata.get('question') is None, 'Part forecast must not use a question')
        cutoff = metadata.get('training_cutoff'); dates = metadata.get('source_dates')
        require(isinstance(cutoff, str) and date.fromisoformat(cutoff).isoformat() == cutoff, 'Exact part training cutoff required')
        require(isinstance(dates, dict) and set(dates) == set(families) == {r['article_id'] for r in references}, 'Exact part source dates and families required')
        require(all(isinstance(d, str) and date.fromisoformat(d).isoformat() == d and d <= cutoff for d in dates.values()), 'Future or imprecise part source date')
        maps = []
        for ref in references:
            validate_reference(ref)
            m = self.maps.get(ref['article_id'], ref['pipeline_id'], owner, ref['run_id'])
            if m is None: raise ArticleMapNotFound('Part source map missing')
            require(m['article_id'] == ref['article_id'] and m['run_id'] == ref['run_id'], 'Part source identity differs')
            maps.append(m)
        require(len({m['source']['sha256'] for m in maps}) == len(maps), 'Repeated part source text')
        coverage = audit_corpus(maps, metadata)
        binding = {'references': references, 'map_hashes': [fingerprint(m) for m in maps], 'families': families,
            'metadata': metadata, 'implementation': implementation, 'version': VERSION, 'limits': LIMITS,
            'context_audit_sha256': fingerprint(context_audit), 'model_audit_sha256': fingerprint(model_audit),
            'origin_audit_sha256': fingerprint(origin_audit)}
        if compound_licenses is not None:
            binding['compound_licenses_sha256'] = fingerprint(compound_licenses)
        if method_clauses is not None:
            binding['method_clauses_sha256'] = fingerprint(method_clauses)
        if role_bindings is not None:
            binding['role_bindings_sha256'] = fingerprint(role_bindings)
        run = fingerprint(binding); previous = self.store.read_seal(run)
        if previous is not None:
            require(previous['binding'] == binding, 'Part forecast binding changed'); return previous
        log.info('semantic_part_forecast_start run=%s sources=%d', run, len(maps))
        artifact = {'run_id': run, 'binding': binding, 'input_corpus_audit': coverage,
            **forecast_parts(maps, families, context_audit, model_audit, origin_audit, compound_licenses,
                             metadata.get('protocol_parameters_enabled', True), method_clauses, role_bindings)}
        self.store.seal(run, artifact)
        log.info('semantic_part_forecast_sealed run=%s blocks=%d parts=%d graph_candidates=%d seconds=%.3f',
            run, artifact['canonical_blocks'], artifact['licensed_parts'], len(artifact['predictions']['graph']), perf_counter() - started)
        return self.store.read_seal(run)

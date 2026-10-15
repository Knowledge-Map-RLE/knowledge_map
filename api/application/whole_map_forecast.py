"""Фиксация свободного прогноза полного корпуса до загрузки целей."""
import logging
from datetime import date
from application.ports.article_comparisons import ComparisonMaps
from application.ports.development_prediction import PredictionStore
from application.compare_article_maps import validate_reference
from domain.article_maps import fingerprint, require, ArticleMapNotFound
from domain.comparison_normalization import VERSION as NORMALIZER_VERSION, DICTIONARY_SHA256
from domain.whole_map_forecast import forecast, VERSION, LIMITS
from domain.whole_map_input_audit import audit_corpus

log = logging.getLogger(__name__)


class SealWholeMapForecast:
    def __init__(self, maps: ComparisonMaps, store: PredictionStore):
        self.maps, self.store = maps, store

    def execute(self, sources, families, owner, metadata, implementation, context_audit=None, model_audit=None, origin_audit=None, categorical_licenses=None):
        require(len(sources) >= 2 and len({r['article_id'] for r in sources}) == len(sources), 'Explicit distinct source maps required')
        require(metadata.get('question') is None, 'Whole-map forecast must not use a question')
        cutoff = metadata.get('training_cutoff')
        require(isinstance(cutoff, str) and date.fromisoformat(cutoff).isoformat() == cutoff, 'Exact training cutoff required')
        dates = metadata.get('source_dates')
        require(isinstance(dates, dict) and set(dates) == {r['article_id'] for r in sources}, 'Explicit source dates required')
        require(all(isinstance(v, str) and date.fromisoformat(v).isoformat() == v and v <= cutoff for v in dates.values()),
                'Future or imprecisely dated source in training')
        maps = []
        for ref in sources:
            validate_reference(ref)
            result = self.maps.get(ref['article_id'], ref['pipeline_id'], owner, ref['run_id'])
            if result is None:
                raise ArticleMapNotFound('Source map missing')
            require(result['article_id'] == ref['article_id'] and result['run_id'] == ref['run_id'], 'Source identity differs')
            maps.append(result)
        require(len({m['source']['sha256'] for m in maps}) == len(maps), 'Repeated source text is not independent support')
        corpus_audit = audit_corpus(maps, metadata)
        binding = {'sources': sources, 'families': families, 'metadata': metadata,
                   'map_hashes': [fingerprint(m) for m in maps], 'version': VERSION, 'limits': LIMITS,
                   'normalizer': NORMALIZER_VERSION, 'dictionary_sha256': DICTIONARY_SHA256,
                   'context_audit_sha256': fingerprint(context_audit) if context_audit else None,
                   'categorical_licenses_sha256': fingerprint(categorical_licenses) if categorical_licenses else None,
                   'origin_audit_sha256': fingerprint(origin_audit) if origin_audit else None,
                   'implementation': implementation, 'model_audit_sha256': fingerprint(model_audit) if model_audit else None}
        run_id = fingerprint(binding)
        previous = self.store.read_seal(run_id)
        if previous is not None:
            require(previous['binding'] == binding, 'Immutable binding changed')
            return previous
        log.info('whole_map_forecast start run=%s sources=%d', run_id, len(maps))
        artifact = {'run_id': run_id, 'binding': binding, 'input_corpus_audit': corpus_audit, **forecast(maps, families, context_audit, model_audit, origin_audit, categorical_licenses)}
        self.store.seal(run_id, artifact)
        log.info('whole_map_forecast sealed run=%s blocks=%d rules=%d graph_candidates=%d',
                 run_id, artifact['canonical_blocks'], len(artifact['rules']), len(artifact['predictions']['graph']))
        return self.store.read_seal(run_id)

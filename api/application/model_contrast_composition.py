"""Оператор получает только явные неизменяемые карты и публикует результат после полной проверки."""
from datetime import date
import logging
from time import perf_counter

from application.compare_article_maps import validate_reference
from application.ports.article_comparisons import ComparisonMaps
from application.ports.development_prediction import PredictionStore
from domain.article_maps import ArticleMapNotFound, fingerprint, require
from domain.model_contrast_composition import compose_model_contrasts, VERSION, LIMITS
from domain.whole_map_input_audit import audit_corpus

log = logging.getLogger(__name__)


class SealModelContrastComposition:
    def __init__(self, maps: ComparisonMaps, store: PredictionStore):
        self.maps, self.store = maps, store

    def execute(self, references, families, owner, metadata, implementation, context_audit, model_audit, origin_audit):
        start = perf_counter()
        ids = {r['article_id'] for r in references}
        require(len(ids) == len(references) >= 2, 'Explicit distinct contrast source maps required')
        require(metadata.get('question') is None, 'Contrast composition must be question-free')
        cutoff = metadata.get('training_cutoff'); dates = metadata.get('source_dates')
        require(isinstance(cutoff, str) and date.fromisoformat(cutoff).isoformat() == cutoff, 'Exact contrast cutoff required')
        require(isinstance(dates, dict) and set(dates) == set(families) == ids, 'Exact contrast source dates and families required')
        require(all(isinstance(d, str) and date.fromisoformat(d).isoformat() == d and d <= cutoff for d in dates.values()),
                'Future or imprecise contrast source date')
        maps = []
        for ref in references:
            validate_reference(ref)
            m = self.maps.get(ref['article_id'], ref['pipeline_id'], owner, ref['run_id'])
            if m is None: raise ArticleMapNotFound('Contrast source map unavailable')
            require(m['article_id'] == ref['article_id'] and m['run_id'] == ref['run_id'], 'Contrast map identity differs')
            maps.append(m)
        require(len({m['source']['sha256'] for m in maps}) == len(maps), 'Repeated contrast source text')
        coverage = audit_corpus(maps, metadata)
        binding = {'version': VERSION, 'limits': LIMITS, 'references': references, 'families': families,
            'map_hashes': [fingerprint(m) for m in maps], 'metadata': metadata, 'implementation': implementation,
            'context_audit_sha256': fingerprint(context_audit), 'model_audit_sha256': fingerprint(model_audit),
            'origin_audit_sha256': fingerprint(origin_audit)}
        run = fingerprint(binding); previous = self.store.read_seal(run)
        if previous is not None:
            require(previous['binding'] == binding, 'Contrast composition binding changed')
            return previous
        log.info('model_contrast_start run=%s sources=%d', run, len(maps))
        result = compose_model_contrasts(maps, context_audit, model_audit, origin_audit)
        self.store.seal(run, {'run_id': run, 'binding': binding, 'input_corpus_audit': coverage, **result})
        log.info('model_contrast_sealed run=%s blocks=%d consequences=%d seconds=%.3f',
                 run, result['canonical_blocks'], len(result['consequences']), perf_counter() - start)
        return self.store.read_seal(run)

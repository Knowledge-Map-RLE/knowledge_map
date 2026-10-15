"""Явный корпус и контекстные обязательства фиксируются до открытия контрольных результатов."""
from datetime import date
import logging
from time import perf_counter

from application.compare_article_maps import validate_reference
from application.ports.article_comparisons import ComparisonMaps
from application.ports.development_prediction import PredictionStore
from domain.article_maps import ArticleMapNotFound, fingerprint, require
from domain.analogy_transport import discover_analogies, VERSION, LIMITS
from domain.whole_map_input_audit import audit_corpus

log = logging.getLogger(__name__)


class SealAnalogyTransport:
    def __init__(self, maps: ComparisonMaps, store: PredictionStore):
        self.maps, self.store = maps, store

    def execute(self, references, families, owner, metadata, implementation, context_audit, origin_audit):
        started = perf_counter(); ids = {r['article_id'] for r in references}
        require(len(ids) == len(references) >= 2, 'Explicit distinct analogy source maps required')
        require(metadata.get('question') is None, 'Analogy discovery must be question-free')
        cutoff = metadata.get('training_cutoff'); dates = metadata.get('source_dates')
        require(isinstance(cutoff, str) and date.fromisoformat(cutoff).isoformat() == cutoff, 'Exact analogy cutoff required')
        require(isinstance(dates, dict) and set(dates) == set(families) == ids, 'Exact analogy source dates and families required')
        require(all(isinstance(d, str) and date.fromisoformat(d).isoformat() == d and d <= cutoff for d in dates.values()),
                'Future or imprecise analogy source date')
        maps = []
        for ref in references:
            validate_reference(ref)
            m = self.maps.get(ref['article_id'], ref['pipeline_id'], owner, ref['run_id'])
            if m is None: raise ArticleMapNotFound('Analogy source map unavailable')
            require(m['article_id'] == ref['article_id'] and m['run_id'] == ref['run_id'], 'Analogy map identity differs')
            maps.append(m)
        require(len({m['source']['sha256'] for m in maps}) == len(maps), 'Repeated analogy source text')
        coverage = audit_corpus(maps, metadata)
        binding = {'version': VERSION, 'limits': LIMITS, 'references': references, 'families': families,
            'map_hashes': [fingerprint(m) for m in maps], 'metadata': metadata, 'implementation': implementation,
            'context_audit_sha256': fingerprint(context_audit), 'origin_audit_sha256': fingerprint(origin_audit)}
        run = fingerprint(binding); previous = self.store.read_seal(run)
        if previous is not None:
            require(previous['binding'] == binding, 'Analogy binding changed'); return previous
        log.info('analogy_transport_start run=%s sources=%d', run, len(maps))
        result = discover_analogies(maps, families, context_audit, origin_audit)
        self.store.seal(run, {'run_id': run, 'binding': binding, 'input_corpus_audit': coverage, **result})
        log.info('analogy_transport_sealed run=%s blocks=%d hypotheses=%d tasks=%d seconds=%.3f',
            run, result['canonical_blocks'], len(result['hypotheses']), len(result['transport_tasks']), perf_counter() - started)
        return self.store.read_seal(run)

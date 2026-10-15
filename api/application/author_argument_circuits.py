"""Явный обучающий корпус проверяется до неизменяемой публикации авторских цепочек."""
from datetime import date
from time import perf_counter
import logging

from application.compare_article_maps import validate_reference
from application.ports.article_comparisons import ComparisonMaps
from application.ports.development_prediction import PredictionStore
from domain.article_maps import require, fingerprint, ArticleMapNotFound
from domain.author_argument_circuits import build_circuits, VERSION, LIMITS
from domain.semantic_operator_graph import build_graph, VERSION as GRAPH_VERSION
from domain.evidence_origin_audit import validate_origins
from domain.whole_map_input_audit import audit_corpus

log = logging.getLogger(__name__)


class SealAuthorArgumentCircuits:
    def __init__(self, maps: ComparisonMaps, store: PredictionStore):
        self.maps, self.store = maps, store

    def execute(self, references, owner, metadata, implementation, context_audit, origin_audit):
        started = perf_counter()
        require(len(references) >= 2 and len({r['article_id'] for r in references}) == len(references), 'Explicit distinct source maps required')
        require(metadata['question'] is None and metadata['model_calls'] == 0 and metadata['target_read'] is False,
            'Source-only free analysis required')
        cutoff, dates = metadata['training_cutoff'], metadata['source_dates']
        require(date.fromisoformat(cutoff).isoformat() == cutoff and set(dates) == {r['article_id'] for r in references},
            'Exact source dates required')
        require(all(date.fromisoformat(d).isoformat() == d and d <= cutoff for d in dates.values()), 'Future source forbidden')
        excluded = metadata['excluded_source_sha256']
        require(isinstance(excluded, list) and bool(excluded) and len(excluded) == len(set(excluded)), 'Explicit excluded target hashes required')
        maps = []
        for ref in references:
            validate_reference(ref)
            m = self.maps.get(ref['article_id'], ref['pipeline_id'], owner, ref['run_id'])
            if m is None: raise ArticleMapNotFound('Argument source missing')
            require(m['article_id'] == ref['article_id'] and m['run_id'] == ref['run_id'], 'Argument source identity differs')
            require(m['source']['sha256'] not in excluded, 'Excluded target entered the source corpus')
            maps.append(m)
        require(len({m['source']['sha256'] for m in maps}) == len(maps), 'Repeated argument source text')
        coverage = audit_corpus(maps, metadata)
        origins = validate_origins(maps, origin_audit)
        binding = {'references': references, 'map_hashes': [fingerprint(m) for m in maps],
            'metadata': metadata, 'implementation': implementation, 'version': VERSION, 'graph_version': GRAPH_VERSION,
            'limits': LIMITS, 'context_audit_sha256': fingerprint(context_audit), 'origin_audit_sha256': fingerprint(origin_audit)}
        run = fingerprint(binding); previous = self.store.read_seal(run)
        if previous is not None:
            require(previous['binding'] == binding, 'Argument snapshot binding differs'); return previous
        log.info('author_argument_circuits_start run=%s sources=%d', run, len(maps))
        graph = build_graph(maps, context_audit); circuits = build_circuits(graph, origins)
        artifact = {'run_id': run, 'binding': binding, 'input_corpus_audit': coverage,
            'semantic_graph': graph, 'argument_circuits': circuits, 'model_calls': 0, 'target_read': False,
            'scientific_success': False, 'graph_advantage_demonstrated': False}
        self.store.seal(run, artifact)
        log.info('author_argument_circuits_sealed run=%s blocks=%d occurrences=%d groups=%d depth=%d seconds=%.3f',
            run, circuits['canonical_blocks'], circuits['visible_occurrences'], len(circuits['groups']), circuits['maximum_depth'], perf_counter() - started)
        return self.store.read_seal(run)

"""Совместимость двух запечатанных срезов проверяется до независимой публикации гипотез."""
import logging
from time import perf_counter

from application.ports.development_prediction import PredictionStore
from domain.article_maps import require, fingerprint, ArticleMapNotFound
from domain.licensed_part_analogy import discover_from_licensed_parts, VERSION, LIMITS

log = logging.getLogger(__name__)


class DiscoverSealedPartAnalogies:
    def __init__(self, parts: PredictionStore, arguments: PredictionStore, output: PredictionStore):
        self.parts, self.arguments, self.output = parts, arguments, output

    def execute(self, parts_run_id, arguments_run_id, origin_audit, implementation):
        started = perf_counter()
        parts = self.parts.read_seal(parts_run_id); arguments = self.arguments.read_seal(arguments_run_id)
        if parts is None or arguments is None: raise ArticleMapNotFound('Explicit sealed analogy input unavailable')
        for run, artifact in ((parts_run_id, parts), (arguments_run_id, arguments)):
            require(fingerprint(artifact['binding']) == run and artifact['run_id'] == run
                    and artifact['target_read'] is False and artifact['model_calls'] == 0,
                    'Source-only immutable run binding required')
            require(artifact['binding']['metadata']['question'] is None, 'Question-free source corpus required')
            require(artifact['binding']['origin_audit_sha256'] == fingerprint(origin_audit), 'Origin audit changed')
        def registry(binding):
            refs = binding['references']; hashes = binding['map_hashes']
            require(len(refs) == len(hashes) and len({r['article_id'] for r in refs}) == len(refs), 'Complete explicit map registry required')
            return {fingerprint(r): h for r, h in zip(refs, hashes)}
        require(registry(parts['binding']) == registry(arguments['binding']), 'Part and argument map versions differ')
        require(parts['binding']['context_audit_sha256'] == arguments['binding']['context_audit_sha256'],
                'Part and argument context audits differ')
        require(parts['binding']['metadata']['training_cutoff'] == arguments['binding']['metadata']['training_cutoff'],
                'Training windows differ')
        excluded = arguments['binding']['metadata'].get('excluded_source_sha256')
        require(isinstance(excluded, list) and bool(excluded), 'Explicit target exclusion required')
        graph = arguments['semantic_graph']
        require(not ({p['source_sha256'] for p in graph['parents'].values()} & set(excluded)), 'Excluded target source in analogy corpus')
        binding = {'parts_run_id': parts_run_id, 'arguments_run_id': arguments_run_id,
            'parts_artifact_sha256': fingerprint(parts), 'arguments_artifact_sha256': fingerprint(arguments),
            'origin_audit_sha256': fingerprint(origin_audit), 'version': VERSION, 'limits': LIMITS,
            'implementation': implementation}
        run = fingerprint(binding); previous = self.output.read_seal(run)
        if previous is not None:
            require(previous['binding'] == binding, 'Analogy immutable binding differs'); return previous
        log.info('licensed_part_analogy_start run=%s parts=%s arguments=%s', run, parts_run_id, arguments_run_id)
        result = {'run_id': run, 'binding': binding,
            **discover_from_licensed_parts(parts, graph, origin_audit, parts['binding']['families'])}
        self.output.seal(run, result)
        log.info('licensed_part_analogy_sealed run=%s parents=%d parts=%d candidates=%d seconds=%.3f',
            run, result['canonical_blocks'], result['admitted_parts'], len(result['all_candidates']), perf_counter() - started)
        return self.output.read_seal(run)

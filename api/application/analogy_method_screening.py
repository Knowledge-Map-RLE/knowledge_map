"""Проверка контроля отделена от генератора и не изменяет зафиксированные гипотезы."""
import logging
from time import perf_counter

from application.ports.development_prediction import PredictionStore
from domain.article_maps import ArticleMapNotFound, fingerprint, require
from domain.analogy_method_screening import screen_method_scope, VERSION

log = logging.getLogger(__name__)


class ScreenSealedAnalogyMethods:
    def __init__(self, protocols: PredictionStore, output: PredictionStore):
        self.protocols, self.output = protocols, output

    def execute(self, run_id, registration, packets, plan, annotation, disclosure, implementation):
        started = perf_counter(); source = self.protocols.read_seal(run_id)
        if source is None: raise ArticleMapNotFound('Explicit sealed source protocols missing')
        require(source['run_id'] == run_id and fingerprint(source['binding']) == run_id
                and registration['source_run_id'] == run_id
                and registration['source_artifact_sha256'] == fingerprint(source), 'Source protocol seal changed')
        require(registration['fixed_original_slots'] == [r['candidate_id'] for r in source['original_budget_slots']],
                'Registered original ranking changed')
        valid = [r for r in source['original_budget_slots'] if r['status'] == 'testable_design_hypothesis_not_confirmed']
        require(registration['eligible_draft_ids'] == [r['candidate_id'] for r in valid], 'Registered draft selection changed')
        for row in valid:
            expected = [w['proposed_protocol'] for w in row['witness_reviews'] if w['proposed_protocol'] is not None]
            require(registration['source_protocols'][row['candidate_id']] == expected, 'Registered design changed')
        binding = {'version': VERSION, 'source_run_id': run_id, 'registration_sha256': fingerprint(registration),
                   'method_plan_sha256': fingerprint(plan), 'packets_sha256': fingerprint(packets),
                   'annotation_sha256': fingerprint(annotation), 'disclosure_sha256': fingerprint(disclosure),
                   'implementation': implementation}
        result = screen_method_scope(registration, packets, plan, annotation, disclosure)
        run = fingerprint(binding); artifact = {'run_id': run, 'binding': binding, **result}
        self.output.seal(run, artifact)
        log.info('analogy_method_scope_sealed run=%s controls=%d comparisons=%d counts=%s seconds=%.3f',
                 run, result['controls_accounted'], len(result['comparisons']), result['counts'], perf_counter() - started)
        return self.output.read_seal(run)

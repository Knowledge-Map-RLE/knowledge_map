"""Явный список источников допускается до формализации и не читает целевую карту."""
import logging
from application.ports.question_prediction import ResearchArtifacts
from domain.article_maps import fingerprint
from domain.methodological_source_screening import VERSION, screen_source_analysis

log = logging.getLogger(__name__)


class AuditMethodologicalSources:
    def __init__(self, artifacts: ResearchArtifacts):
        self.artifacts = artifacts

    def execute(self, records, sources, historical_before):
        if len({r['id'] for r in records}) != len(records):
            raise ValueError('Repeated analytical record')
        rows = [screen_source_analysis(r, sources[r['article_id']], historical_before) for r in records]
        result = {'version': VERSION, 'rows': rows,
                  'eligible_analyses': sum(r['eligible_for_frozen_question'] for r in rows),
                  'eligible_independent_families': sorted({r['record']['family'] for r in rows if r['eligible_for_frozen_question']}),
                  'source_articles': len({r['article_id'] for r in records}), 'model_calls': 0,
                  'clinical_predictions': 0, 'training_changed': False, 'target_selected': False}
        result['run_id'] = fingerprint(result)
        self.artifacts.audit(result['run_id'], result)
        log.info('methodological_screening run=%s articles=%s eligible=%s families=%s',
                 result['run_id'], result['source_articles'], result['eligible_analyses'], len(result['eligible_independent_families']))
        return result

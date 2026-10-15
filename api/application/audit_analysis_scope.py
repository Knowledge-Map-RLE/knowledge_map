"""Сценарий проверяет только явно перечисленные факты и неизменяемо сохраняет решения."""
import logging
from application.ports.question_prediction import ResearchArtifacts
from domain.article_maps import fingerprint
from domain.analysis_scope_transfer import VERSION, audit_scope_transfer

log = logging.getLogger(__name__)

class AuditAnalysisScope:
    def __init__(self, artifacts: ResearchArtifacts):
        self.artifacts = artifacts

    def execute(self, cases, sources):
        if not cases or len({case['id'] for case in cases}) != len(cases):
            raise ValueError('Unique nonempty analytical cases required')
        rows = []
        for case in cases:
            if set(case) != {'id', 'fact', 'target_scope', 'membership', 'note_ru', 'note_en'}:
                raise ValueError('Closed analytical case required')
            rows.append({'id': case['id'], 'note_ru': case['note_ru'], 'note_en': case['note_en'],
                         'decision': audit_scope_transfer(case['fact'], case['target_scope'], case['membership'], sources)})
        result = {'version': VERSION, 'rows': rows,
                  'context_inheritances_allowed': sum(row['decision']['context_inheritance_allowed'] for row in rows),
                  'clinical_predictions': 0, 'model_calls': 0, 'training_changed': False, 'scientific_success': False}
        result['run_id'] = fingerprint(result)
        self.artifacts.audit(result['run_id'], result)
        log.info('analysis_scope_audit run=%s cases=%s context_allowed=%s',
                 result['run_id'], len(rows), result['context_inheritances_allowed'])
        return result

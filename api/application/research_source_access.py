"""Неизменяемый аудит доступа использует только явно переданные документы без AI-клиентов."""
import logging
from application.ports.question_prediction import ResearchArtifacts
from domain.article_maps import fingerprint
from domain.research_source_access import audit_source_access

log = logging.getLogger(__name__)


class AuditResearchSourceAccess:
    def __init__(self, artifacts: ResearchArtifacts):
        self.artifacts = artifacts

    def execute(self, candidate, documents):
        result = audit_source_access(candidate, documents)
        result['run_id'] = fingerprint(result)
        self.artifacts.audit(result['run_id'], result)
        log.info('research_source_access run=%s documents=%s full=%s conflicts=%s ready=%s',
                 result['run_id'], len(documents), len(result['full_text_document_ids']),
                 len(result['conflicts']), result['ready_for_fulltext_formalization'])
        return result

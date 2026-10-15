"""Фиксирует проверку конкретных источников, не добавляя их в обучающий корпус автоматически."""
import logging
from application.ports.question_prediction import ResearchArtifacts
from domain.article_maps import fingerprint, require
from domain.prospective_question_screening import VERSION, validate_screening_record, screen_continuous_mmse

log = logging.getLogger(__name__)


class ScreenProspectiveQuestionSources:
    def __init__(self, artifacts: ResearchArtifacts):
        self.artifacts = artifacts

    def execute(self, sources, records, selection):
        require(selection['cutoff'] == '2022-12-31' and selection['purpose'] == 'historical_training_feasibility_only',
                'Explicit historical feasibility scope required')
        require(len({r['id'] for r in records}) == len(records), 'Duplicated analytic screening record')
        require(set(sources) == {r['source_sha256'] for r in records}, 'Implicit or unreferenced source forbidden')
        results = []
        for record in records:
            source = sources.get(record['source_sha256'])
            require(source is not None and type(source['publication_year']) is int and 1900 <= source['publication_year'] <= 2022
                    and source['kind'] in {'full_primary_article', 'full_primary_author_chapter'},
                    'Future, abstract-only or unknown source cannot establish training eligibility')
            verified = validate_screening_record(record, source)
            results.append(screen_continuous_mmse(verified))
        binding = {'version': VERSION, 'selection': selection, 'records_sha256': fingerprint(records),
                   'sources': [{'sha256': s['sha256'], 'publication_year': s['publication_year'], 'kind': s['kind']}
                               for _, s in sorted(sources.items())]}
        result = {'run_id': fingerprint(binding), 'binding': binding, 'results': results,
                  'eligible_records': sum(r['eligible_for_subquestion'] for r in results),
                  'eligible_families': sorted({r['family'] for r in results if r['eligible_for_subquestion']}),
                  'model_calls': 0, 'new_training_sources': 0, 'future_target_selected': False,
                  'forecast_issued': False, 'expert_validated': False}
        self.artifacts.audit(result['run_id'], result)
        log.info('prospective_screening run=%s records=%s eligible=%s families=%s',
                 result['run_id'], len(records), result['eligible_records'], len(result['eligible_families']))
        return result

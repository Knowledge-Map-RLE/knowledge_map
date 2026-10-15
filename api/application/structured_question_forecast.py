"""Независимые сценарии запечатывания прогноза и чтения известных исходов."""
import logging
from domain.article_maps import fingerprint, require
from domain.structured_question_forecast import forecast, evaluate
from application.ports.structured_question_forecast import StructuredTrainingCorpus, StructuredTargetOutcomes, StructuredForecastArtifacts

log = logging.getLogger(__name__)

class SealStructuredForecast:
    def __init__(self, corpus: StructuredTrainingCorpus, artifacts: StructuredForecastArtifacts):
        self.corpus, self.artifacts = corpus, artifacts

    def execute(self, references, diagnostic_metadata):
        require(references and len(references) == len(set(references)), 'Unique explicit target contexts required')
        require(diagnostic_metadata == {'already_outcome_exposed': True, 'blind_scientific_test': False}, 'This scenario is retrospective diagnostic only')
        predictions = []
        for reference in references:
            request = self.corpus.context(reference)
            observations = self.corpus.earlier_other_families(request['family'], request['available_on'])
            for view in ('reported_study_horizon', 'verified_individual_minimum'):
                for model in ('family_frequency', 'categorical_naive_bayes'):
                    predictions.append(forecast(observations, request, model, view))
        result = {'predictions': predictions, 'diagnostic_metadata': diagnostic_metadata,
                  'new_blind_predictions': 0, 'scientific_success': False}
        run_id = fingerprint(result)
        self.artifacts.seal(run_id, result)
        log.info('structured_forecast_sealed run=%s targets=%s forecasts=%s', run_id, len(references), len(predictions))
        return run_id

class EvaluateStructuredForecast:
    def __init__(self, targets: StructuredTargetOutcomes, artifacts: StructuredForecastArtifacts):
        self.targets, self.artifacts = targets, artifacts

    def execute(self, run_id):
        sealed = self.artifacts.read_seal(run_id)
        require(fingerprint(sealed) == run_id, 'Sealed artifact changed')
        rows = []
        for prediction in sealed['predictions']:
            reference = prediction['request']['reference']
            target = self.targets.outcome(reference)
            rows.append({'reference': reference, 'family': target['family'], 'model': prediction['model'],
                         'temporal_view': prediction['temporal_view'], 'scores': evaluate(prediction, target)})
        result = {'sealed_run_id': run_id, 'rows': rows, 'scientific_success': False,
                  'blind_scientific_test': False, 'new_clinical_predictions': 0}
        evaluation_id = fingerprint(result)
        self.artifacts.evaluate(run_id, evaluation_id, result)
        log.info('structured_forecast_evaluated run=%s evaluation=%s rows=%s', run_id, evaluation_id, len(rows))
        return evaluation_id, result

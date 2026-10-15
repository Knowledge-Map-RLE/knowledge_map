"""Оценка читает зафиксированный прогноз и отдельный контроль; обучение не вызывается."""
from domain.article_maps import fingerprint, require
from domain.mechanistic_evaluation import evaluate


class EvaluateMechanisticOpportunities:
    def __init__(self, predictions, controls):
        self.predictions, self.controls = predictions, controls

    def execute(self, run_id, plan, control_id, implementation):
        forecast = self.predictions.read_seal(run_id)
        require(forecast is not None, 'Frozen forecast missing')
        control, source = self.controls.get(control_id)
        result = evaluate(forecast, plan, control, source)
        binding = {'forecast_sha256': fingerprint(forecast), 'control_sha256': fingerprint(control),
                   'source_sha256': fingerprint(source), 'plan_sha256': fingerprint(plan), 'implementation': implementation}
        result = {**result, 'evaluation_id': fingerprint(binding), 'binding': binding}
        self.predictions.save_evaluation(run_id, result['evaluation_id'], result)
        return result

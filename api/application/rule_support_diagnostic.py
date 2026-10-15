"""Неизменяемая диагностика проверенного прогноза не открывает целевую статью."""
import logging
from time import perf_counter

from domain.article_maps import require, fingerprint
from domain.rule_support_diagnostic import diagnose_support, VERSION, MODES

logger = logging.getLogger(__name__)


class SealRuleSupportDiagnostic:
    def __init__(self, forecasts, snapshots):
        self.forecasts, self.snapshots = forecasts, snapshots

    def execute(self, forecast_run, implementation):
        started = perf_counter()
        forecast = self.forecasts.read_seal(forecast_run)
        require(forecast is not None and forecast['run_id'] == forecast_run, 'Explicit forecast seal required')
        binding = {'forecast_run': forecast_run, 'forecast_sha256': fingerprint(forecast),
            'forecast_binding': forecast['binding'], 'version': VERSION,
            'modes': {k: sorted(v) for k, v in MODES.items()}, 'implementation': implementation}
        run = fingerprint(binding); previous = self.snapshots.read_seal(run)
        if previous is not None:
            require(previous['binding'] == binding, 'Diagnostic binding changed')
            return previous
        logger.info('rule_support_diagnostic_start forecast=%s run=%s', forecast_run, run)
        artifact = {'run_id': run, 'binding': binding, **diagnose_support(forecast), 'target_read': False}
        self.snapshots.seal(run, artifact)
        logger.info('rule_support_diagnostic_sealed run=%s blocks=%s templates=%s seconds=%.3f',
                    run, artifact['canonical_blocks'], artifact['template_count'], perf_counter() - started)
        return self.snapshots.read_seal(run)

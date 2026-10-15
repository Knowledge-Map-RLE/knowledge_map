"""Фиксация внешних кандидатов предшествует открытию отдельного порта исходов."""
import logging
from time import perf_counter
from typing import Protocol

from application.ports.development_prediction import PredictionStore
from domain.article_maps import fingerprint, require
from domain.external_operation_transfer import VERSION, forecast_external, evaluate_external

log = logging.getLogger(__name__)


class ExternalReceiverPort(Protocol):
    def load(self): ...


class ExternalOutcomePort(Protocol):
    def load(self): ...


class SealExternalOperationTransfer:
    def __init__(self, training, receivers: ExternalReceiverPort, outcomes: ExternalOutcomePort, store: PredictionStore):
        self.training, self.receivers, self.outcomes, self.store = training, receivers, outcomes, store

    def execute(self, implementation):
        started = perf_counter(); training = self.training.load(); receivers = self.receivers.load()
        binding = {'version': VERSION, 'input_run_id': training['input_run_id'],
            'input_sha256': training['input_sha256'], 'receiver_packet_sha256': fingerprint(receivers),
            'author_groups_sha256': fingerprint(training['author_groups']), 'implementation': implementation}
        run = fingerprint(binding); result = self.store.read_seal(run)
        if result is None:
            log.info('external_operation_transfer_start run=%s receivers=%d', run, len(receivers['receivers']))
            result = {'run_id': run, 'binding': binding, **forecast_external(training, receivers)}
            self.store.seal(run, result); result = self.store.read_seal(run)
        require(result['binding'] == binding, 'External forecast input changed')
        # Ошибка исходов не влияет на уже опубликованный неизменяемый прогноз.
        evaluation = evaluate_external(result, self.outcomes.load())
        evaluation_id = fingerprint(evaluation); self.store.save_evaluation(run, evaluation_id, evaluation)
        log.info('external_operation_transfer_evaluated run=%s evaluation=%s seconds=%.3f',
                 run, evaluation_id, perf_counter() - started)
        return result, evaluation_id, evaluation

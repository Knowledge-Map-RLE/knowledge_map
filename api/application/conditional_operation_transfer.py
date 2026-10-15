"""Сначала фиксирует перенос, затем открывает результаты отдельному оценщику."""
import logging
from time import perf_counter
from typing import Protocol

from application.ports.development_prediction import PredictionStore
from domain.article_maps import fingerprint, require
from domain.conditional_operation_transfer import VERSION, forecast_transfers, evaluate_transfers, reapply_without_holdout

log = logging.getLogger(__name__)


class OperationTransferCorpus(Protocol):
    def load(self): ...
    def outcomes(self): ...


class SealConditionalOperationTransfer:
    def __init__(self, corpus: OperationTransferCorpus, store: PredictionStore):
        self.corpus, self.store = corpus, store

    def execute(self, implementation):
        started = perf_counter()
        payload = self.corpus.load()
        binding = {'version': VERSION, 'input_run_id': payload['input_run_id'],
                   'input_sha256': payload['input_sha256'], 'implementation': implementation,
                   'receiver_projection_sha256': fingerprint(payload['receivers']),
                   'author_groups_sha256': fingerprint(payload['author_groups'])}
        run = fingerprint(binding)
        previous = self.store.read_seal(run)
        if previous is None:
            log.info('conditional_operation_transfer_start run=%s receivers=%d', run, len(payload['receivers']))
            result = {'run_id': run, 'binding': binding,
                      **forecast_transfers(payload['cases'], payload['receivers'], payload['author_groups'], payload['coverage'])}
            self.store.seal(run, result)
            previous = self.store.read_seal(run)
        require(previous['binding'] == binding, 'Transfer input binding changed')
        # Даже ошибка оценщика не стирает зафиксированное предсказание.
        evaluation = evaluate_transfers(previous, self.corpus.outcomes())
        evaluation['resubstitution_diagnostic'] = reapply_without_holdout(
            payload['cases'], payload['receivers'], payload['author_groups'])
        evaluation_id = fingerprint(evaluation)
        self.store.save_evaluation(run, evaluation_id, evaluation)
        log.info('conditional_operation_transfer_evaluated run=%s evaluation=%s seconds=%.3f',
                 run, evaluation_id, perf_counter() - started)
        return previous, evaluation_id, evaluation

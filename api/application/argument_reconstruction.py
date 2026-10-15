"""Сценарий запечатанного инженерного прогона, без доступа к оценочной цели."""
from typing import Protocol

from domain.argument_reconstruction import reconstruct
from domain.article_maps import fingerprint


class ReconstructionStore(Protocol):
    def seal(self, key: str, value: dict) -> None: ...


def run_reconstruction(requests: dict, store: ReconstructionStore) -> dict:
    # Порт оценщика намеренно отсутствует: цель не передаётся генератору.
    store.seal('requests.json', requests)
    outputs = {key: reconstruct(request) for key, request in requests.items()}
    sealed = {'requests_sha256': fingerprint(requests), 'outputs': outputs,
              'retrospective_engineering_only': True, 'model_calls': 0, 'training_performed': False}
    store.seal('sealed-output.json', sealed)
    return sealed

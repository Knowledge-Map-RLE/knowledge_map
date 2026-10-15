"""Запечатывает предложения задач без порта чтения оценочных заключений."""
from typing import Protocol

from domain.article_maps import fingerprint
from domain.limitation_task_proposals import propose_tasks


class ProposalStore(Protocol):
    def seal(self, key: str, value: dict) -> None: ...


def run_task_proposals(requests: dict, store: ProposalStore) -> dict:
    store.seal('requests.json', requests)
    result = {'requests_sha256': fingerprint(requests), 'outputs': {cid: propose_tasks(q) for cid,q in requests.items()},
              'model_calls': 0, 'training_performed': False, 'clinical_forecasts': 0}
    store.seal('sealed-output.json', result)
    return result

"""Отдельные пакеты контекстов и числовых представлений."""
from typing import Protocol


class BridgeCorpus(Protocol):
    def contexts(self) -> dict: ...
    def mathematical_cases(self) -> dict: ...


class BridgeStore(Protocol):
    def seal(self, run_id: str, artifact: dict) -> None: ...

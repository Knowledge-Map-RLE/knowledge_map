"""Порт загружает только заранее подготовленные разбиения источников."""
from typing import Protocol


class CohortTransferInputs(Protocol):
    def read_inputs(self) -> dict: ...

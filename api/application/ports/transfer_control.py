"""Порт отдельного оценщика, имеющего доступ к контрольному источнику."""
from typing import Protocol


class ControlInputs(Protocol):
    def read_inputs(self) -> dict: ...

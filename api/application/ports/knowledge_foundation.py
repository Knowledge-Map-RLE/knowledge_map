"""Порты обучения и отдельного контроля фундаментальных преобразований."""
from typing import Protocol

class FoundationInputs(Protocol):
    def read_inputs(self) -> dict: ...

class FoundationControls(Protocol):
    def read_controls(self) -> dict: ...

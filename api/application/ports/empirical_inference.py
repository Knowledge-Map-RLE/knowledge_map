"""Раздельные порты входов и скрытых контролей эмпирического опыта."""
from typing import Protocol


class EmpiricalInputs(Protocol):
    def read_inputs(self) -> dict: ...


class EmpiricalControls(Protocol):
    def read_controls(self) -> dict: ...

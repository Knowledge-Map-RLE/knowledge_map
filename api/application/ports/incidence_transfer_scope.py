"""Порт принимает только явные разбиения и типизированный контекст без ответов."""
from typing import Protocol


class IncidenceScopeInputs(Protocol):
    def read_inputs(self)->dict: ...

"""Порт только обучающих знаний для фиксации независимого контроля."""
from typing import Protocol

class TransferInputs(Protocol):
    def read_inputs(self)->dict: ...

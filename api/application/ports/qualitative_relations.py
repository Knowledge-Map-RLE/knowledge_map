"""Порт явно ограниченных входов качественного опыта."""
from typing import Protocol

class QualitativeInputs(Protocol):
    def read_inputs(self)->dict:...

class QualitativeControls(Protocol):
    def read_controls(self)->dict:...

"""Порты явного обучающего входа и последующего аудита применимости."""
from typing import Protocol

class MechanismInputs(Protocol):
    def read_inputs(self) -> dict: ...

class MechanismProfiles(Protocol):
    def read_profiles(self) -> dict: ...

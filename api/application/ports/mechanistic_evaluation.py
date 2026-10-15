"""Порт явно перечисленных контрольных артефактов, без доступа к обучающему корпусу."""
from typing import Protocol


class MechanisticControls(Protocol):
    def get(self, control_id: str) -> tuple[dict, dict]: ...

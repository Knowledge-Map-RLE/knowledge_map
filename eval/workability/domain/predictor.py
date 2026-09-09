"""
Domain — интерфейс движка предсказаний (предиктора).

Это pluggable-точка для будущей системы предсказаний. Каркас проверки
работоспособности зависит ТОЛЬКО от этого интерфейса (Принцип инверсии
зависимостей, Open/Closed). В будущем сюда подключат rule-based / ML / LLM
движок БЕЗ изменения каркаса метрик и backtest-оркестратора.

Сейчас единственная реализация — baseline (Random / Popularity) в baseline.py.
"""
from __future__ import annotations

from typing import List, Protocol, runtime_checkable

from .statements import TemporalSnapshot


@runtime_checkable
class PredictionEngine(Protocol):
    """Контракт любого предиктора утверждений."""

    name: str

    def predict(
        self,
        snapshot: TemporalSnapshot,
        source_nk: str,
        k: int,
    ) -> List[str]:
        """Возвращает ранжированный список top-K кандидатов-утверждений (norm_key).

        Args:
            snapshot: исторический граф знаний на момент времени T
                      (содержит только данные <= T — без утечки будущего).
            source_nk: каноническое утверждение исходной статьи, от которого
                       идёт прогноз.
            k: желаемое число кандидатов.

        Returns:
            список norm_key длины <= k, упорядоченный по убыванию уверенности.
        """
        ...

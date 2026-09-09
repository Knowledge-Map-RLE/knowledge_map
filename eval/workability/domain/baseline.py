"""
Domain — Baseline-предикторы (без истинной предсказательной силы).

Baseline нужны, чтобы понять, хороша ли КЗ (документ, §21). Без сравнения с
простым фоном метрики ничего не доказывают.

В первом релизе реализованы:
  - RandomBaseline:    случайный ранжированный список кандидатов.
  - PopularityBaseline: наиболее частые утверждения в историческом графе
                        (литературный "популярностный" фон).
"""
from __future__ import annotations

import random
from typing import List

from .statements import TemporalSnapshot


class RandomBaseline:
    """Случайно выбирает кандидатов из утверждений исторического графа.

    Random — критический нижний предел. Если будущий rule-based предиктор не
    превзойдёт Random по Precision@K/Recall@K, значит предсказательной силы нет.

    Note: семплирование без повторений, поэтому результат детерминирован при
    фиксированном seed. Использование crypto-рандома не требуется.
    """

    name = "random"

    def __init__(self, seed: int = 42) -> None:
        self._rng = random.Random(seed)

    def predict(self, snapshot: TemporalSnapshot, source_nk: str, k: int) -> List[str]:
        pool = sorted(snapshot.all_statement_keys)
        if not pool:
            return []
        candidates = self._rng.sample(pool, min(k, len(pool)))
        # Ранжируем "случайным" произвольным порядком -> просто перемешиваем.
        self._rng.shuffle(candidates)
        return candidates


class PopularityBaseline:
    """Выбирает наиболее часто встречающиеся утверждения в историческом графе.

    Отражает "популярность" знания: часто цитируемые/повторяемые утверждения.
    Не предсказывает будущее, но полезен как sanity-check фона.
    """

    name = "popularity"

    def __init__(self, k_statement_docs: bool = True) -> None:
        # Используем число статей, содержащих norm_key, как частоту.
        self._k_statement_docs = k_statement_docs

    def predict(self, snapshot: TemporalSnapshot, source_nk: str, k: int) -> List[str]:
        # Считаем, в скольких статьях встречается каждое утверждение.
        frequency: dict[str, int] = {}
        for art in snapshot.articles.values():
            for nk in art.statements:
                frequency[nk] = frequency.get(nk, 0) + 1

        # Частотный топ-K (устойчивый порядок по убыванию, затем по ключу).
        ranked = sorted(frequency.items(), key=lambda kv: (-kv[1], kv[0]))
        return [nk for nk, _ in ranked[:k]]

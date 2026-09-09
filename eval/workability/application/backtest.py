"""
Application — оркестратор backtesting работоспособности КЗ.

Реализует честную схему временного split (rolling origin по годам publication_date),
с описанной в docs/ИИ. Предсказание статей и триплетов.md логикой:

  Для каждой контрольной точки T:
    KnowledgeGraph(T)  = статьи/утверждения/рёбра с publication_date <= T
    source_nk           = каноническое утверждение исходной статьи (<= T)
    predicted           = PredictionEngine.predict(snapshot(T), source_nk, k)
    real_future         = утверждения статей в окне (T, T+H]   [эталон]

KPI-1: Precision@K / Recall@K / F1@K / MRR / Hits@K  (predicted vs real_future)
KPI-2: графовое расстояние source_nk -> будущее утверждение на snapshot(T),
       mean/median/max/P90 + Long-range Recall@K(d >= D)

БЕЗ утечки будущего: предиктор видит только snapshot(T); расстояния считаются
на snapshot(T), а не на полном графе.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Protocol, Sequence

from ..domain import metrics as mtr
from ..domain.distances import all_shortest_distances
from ..domain.predictor import PredictionEngine
from ..domain.statements import TemporalSnapshot

logger = logging.getLogger(__name__)


@dataclass
class BacktestConfig:
    """Конфигурация прогона backtest.

    Attributes:
        start_year:  первая контрольная точка T.
        end_year:    последняя контрольная точка T (включительно).
        step:        шаг по годам между контрольными точками.
        horizon:     H — ширина окна будущего (T, T+H] для сбора эталона.
        k:           топ-K предсказаний, по которому оцениваем.
        min_distance: порог D для Long-range Recall@K(d >= D).
        ratio:       семплировать не более этой доли статей ≤ T как источники
                     прогноза (для масштабируемости на миллионы статей).
        max_source_per_year: жёсткий предел числа source-утверждений на год.
    """
    start_year: int = 2000
    end_year: int = 2025
    step: int = 1
    horizon: int = 5
    k: int = 10
    min_distance: int = 10
    ratio: float = 0.05
    max_source_per_year: int = 2000


@dataclass
class CaseResult:
    """Результат одного тестового случая (одна source-точка прогноза)."""
    year: int
    source_nk: str
    source_doc_id: str
    predicted: List[str]
    real: List[str]
    kpi1: Dict[str, float]
    distances: Dict[str, Optional[int]] = field(default_factory=dict)


@dataclass
class YearResult:
    """Агрегированный результат по одной контрольной точке T."""
    year: int
    n_cases: int
    snapshot_size: int  # число статей в snapshot(T)
    kpi1_avg: Dict[str, float]
    distance_stats: Dict[str, float]  # mean/median/max/p90 по успешным предсказаниям
    longrange_recall: float


class Backtester:
    """Проводит backtest по временным срезам и собирает результаты KPI."""

    def __init__(
        self,
        predictor: PredictionEngine,
        config: BacktestConfig,
    ) -> None:
        self.predictor = predictor
        self.config = config

    # ─── Основной прогон ─────────────────────────────────────────────── #

    def run(
        self,
        snapshot_factory,
        real_future_getter,
        source_getter,
    ) -> List[YearResult]:
        """Запускает backtest по всем контрольным точкам T.

        Args:
            snapshot_factory: callable(year) -> TemporalSnapshot  (граф <= T)
            real_future_getter: callable(snapshot, real_year) ->
                                (year_map, Dict[doc_id, Set[norm_key]])
                                Возвращает реальные будущие статьи в окне
                                (T, T+H] — фактический эталон. (Смотри CLIRunner,
                                использует snapshot.articles_after).
            source_getter: callable(snapshot, limit) -> List[(doc_id, source_nk)]
                                выбор исходных статей/утверждений для прогноза.

        Returns:
            список YearResult по каждой контрольной точке.
        """
        cfg = self.config
        results: List[YearResult] = []

        for T in range(cfg.start_year, cfg.end_year + 1, cfg.step):
            snapshot = snapshot_factory(T)
            real_year = T + cfg.horizon

            # 1. Будущие статьи (эталон) в окне (T, T+H]
            future_year_map, future_articles = real_future_getter(snapshot, real_year)
            # norm_key -> год первого появления
            first_year: Dict[str, int] = {}
            for doc_id, nks in future_articles.items():
                y = future_year_map.get(doc_id, real_year)
                for nk in nks:
                    if nk not in first_year or y < first_year[nk]:
                        first_year[nk] = y

            # Реальные будущие утверждения в окне
            real = sorted(first_year.keys())

            # 2. Источники прогноза в snapshot(T)
            sources = source_getter(snapshot, cfg.max_source_per_year)

            year_case_results: List[CaseResult] = []

            for src_doc_id, source_nk in sources:
                # Предиктор на snapshot(T) — БЕЗ утечки будущего.
                predicted = self.predictor.predict(snapshot, source_nk, cfg.k)
                if not predicted:
                    continue

                # KPI-1
                kpi1 = mtr.ranking_metrics(predicted, real, cfg.k)

                # KPI-2: расстояния на snapshot(T) от source до реальных будущих
                distances = all_shortest_distances(
                    snapshot, source_nk, list(real), source_doc=src_doc_id
                )

                year_case_results.append(
                    CaseResult(
                        year=T,
                        source_nk=source_nk,
                        source_doc_id=src_doc_id,
                        predicted=predicted,
                        real=real,
                        kpi1=kpi1,
                        distances=distances,
                    )
                )

            results.append(self._aggregate_year(T, snapshot, year_case_results, real))

        return results

    # ─── Агрегация по году ────────────────────────────────────────────── #

    def _aggregate_year(
        self,
        T: int,
        snapshot: TemporalSnapshot,
        cases: List[CaseResult],
        real: List[str],
    ) -> YearResult:
        if not cases:
            k = self.config.k
            return YearResult(
                year=T,
                n_cases=0,
                snapshot_size=len(snapshot.articles),
                kpi1_avg={
                    f"precision@{k}": 0.0,
                    f"recall@{k}": 0.0,
                    f"f1@{k}": 0.0,
                    "mrr": 0.0,
                    f"hits@{k}": 0.0,
                },
                distance_stats=mtr.distance_stats([]),
                longrange_recall=0.0,
            )

        kpi1_avg = mtr.aggregate_ranking_metrics([c.kpi1 for c in cases])

        # KPI-2: собираем расстояния успешных предсказаний (попали в top-K)
        # Здесь "успешное предсказание" = будущее утверждение, которое (а) в top-K,
        # (б) достижимо в графе snapshot(T) от source.
        dist_values: List[int] = []
        for c in cases:
            top_k = set(c.predicted[: self.config.k])
            for nk in real:
                if nk in top_k:
                    d = c.distances.get(nk)
                    if d is not None:
                        dist_values.append(d)

        dist_stats = mtr.distance_stats(dist_values)

        # Long-range Recall@K: по всем случаям года.
        # Для каждого случая считаем recall@K(d>=D) и усредняем.
        lr_recalls = []
        for c in cases:
            lr = mtr.longrange_recall_at_k(
                c.predicted, real, c.distances, self.config.min_distance, self.config.k
            )
            lr_recalls.append(lr)
        longrange_recall = sum(lr_recalls) / len(lr_recalls) if lr_recalls else 0.0

        return YearResult(
            year=T,
            n_cases=len(cases),
            snapshot_size=len(snapshot.articles),
            kpi1_avg=kpi1_avg,
            distance_stats=dist_stats,
            longrange_recall=longrange_recall,
        )

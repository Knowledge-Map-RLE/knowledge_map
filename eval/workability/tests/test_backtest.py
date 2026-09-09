"""
Integration tests: полный цикл backtest на синтетических данных.

Проверяет, что каркас работает end-to-end без Neo4j:
  снапшот(T) → предиктор → real future → KPI-1 (ranking) → KPI-2 (distance).
"""
import sys
from pathlib import Path
from typing import Dict, List, Tuple

EVAL_DIR = Path(__file__).resolve().parent.parent.parent
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

from workability.application.backtest import Backtester, BacktestConfig, YearResult
from workability.domain.statements import CanonicalStatement, Article, TemporalSnapshot
from workability.domain.predictor import PredictionEngine


class FakePredictor:
    """Тестовый предиктор: возвращает заранее заданные norm_key заранее."""

    name = "fake"

    def __init__(self, candidates: List[str]) -> None:
        self.candidates = candidates

    def predict(self, snapshot: TemporalSnapshot, source_nk: str, k: int) -> List[str]:
        return self.candidates[:k]


def _make_snapshot(
    year: int,
    articles: Dict[str, Tuple[int, List[str]]],
    edges: List[Tuple[str, str]],
) -> TemporalSnapshot:
    """Строит TemporalSnapshot из: doc_id -> (год, [norm_key...]).

    edges: рёбра цитирования между DOC_ID (не norm_key) — BIBLIOGRAPHIC_LINK.
    """
    art_objs = {}
    art_years = {}
    for doc_id, (y, nks) in articles.items():
        art_objs[doc_id] = Article(doc_id=doc_id, statements=set(nks))
        art_years[doc_id] = y
    return TemporalSnapshot(
        year=year,
        articles=art_objs,
        article_years=art_years,
        bibliographic_edges=set(edges),
    )


def test_backtest_kpi1_and_kpi2_work():
    """Полный backtest: корректный подсчёт Precision@K и distance."""
    # Снапшоты вручную, без corpus.
    # Статья A в 2020 с утверждением nk_a, статья B в 2024 с nk_b (будущая).
    # Граф: nk_a -> nk_b (путь 1) - уже в графе 2020 (рёбро <=T).
    # Хм: чтобы distance был не-None, target должен быть в графе снапшота.
    # Но будущая статья B содержит НОВЫЙ norm_key, которого нет в snapshot(T).
    # Это реальная семантика: будущее утверждение может не существовать в графе T.
    # Поэтому выбираем: nk_a -> nk_mid, nk_mid -> nk_b - всё в одном графе.

    # Проектируем контролируемый сценарий единым snapshot'ом.
    # Статьи до T=2020: A (nk_a), C (nk_c).
    # Цитирование: A -> C (ребро BIBLIOGRAPHIC_LINK, вес 1).
    # Будущая статья D (2022): содержит nk_c (попадание, distance=1).
    # Будущая статья E (2022): содержит nk_z (не существующий, miss).
    articles = {
        "A": (2018, ["nk_a"]),
        "C": (2019, ["nk_c"]),
        "D": (2022, ["nk_c"]),  # будущая
        "E": (2022, ["nk_z"]),  # будущая
    }
    edges = [("A", "C")]

    # Снапшот T=2020
    snap_2020 = _make_snapshot(2020, articles, edges)

    # Источники: статья A
    sources = [("A", "nk_a")]

    # Предиктор: nk_c на 1-й позиции -> Precision@1 = 1.0, Recall@1 = (nk_c из real)
    predictor = FakePredictor(candidates=["nk_c", "nk_x", "nk_y"])

    cfg = BacktestConfig(
        start_year=2020, end_year=2020, step=1, horizon=2,
        k=3, min_distance=1, ratio=1.0, max_source_per_year=10,
    )
    bt = Backtester(predictor, cfg)

    # callable: snapshot_factory возвращает snap_2020 всегда для T=2020
    def snapshot_factory(year: int) -> TemporalSnapshot:
        return snap_2020

    def real_future_getter(snapshot: TemporalSnapshot, real_year: int):
        # Будущие статьи: D (nk_c), E (nk_z)
        future = {"D": {"nk_c"}, "E": {"nk_z"}}
        years = {"D": 2022, "E": 2022}
        return years, future

    def source_getter(snapshot: TemporalSnapshot, limit: int):
        return sources

    results: List[YearResult] = bt.run(snapshot_factory, real_future_getter, source_getter)

    assert len(results) == 1
    yr = results[0]
    assert yr.year == 2020
    assert yr.n_cases == 1

    # KPI-1: P@3 = 1/3 (nk_c входит), recall@3 = nk_c/ (nk_c,nk_z) = 1/2
    assert abs(yr.kpi1_avg["precision@3"] - 1 / 3) < 1e-9
    assert abs(yr.kpi1_avg["recall@3"] - 1 / 2) < 1e-9
    assert abs(yr.kpi1_avg["f1@3"] - (2 * (1 / 3) * (1 / 2)) / ((1 / 3) + (1 / 2))) < 1e-9
    assert abs(yr.kpi1_avg["mrr"] - 1.0) < 1e-9

    # KPI-2: единственное успешное предсказание nk_c, distance = 1
    assert yr.distance_stats["count"] == 1
    assert yr.distance_stats["mean"] == 1.0
    assert yr.distance_stats["max"] == 1.0

    # Long-range Recall@K(d>=1): nk_c достижим (d=1>=1), так и nk_z не достижим.
    # relevant = [nk_c, nk_z]; far = [nk_c]; hit в top3 = да -> 1.0
    assert abs(yr.longrange_recall - 1.0) < 1e-9


def test_backtest_multiple_years_uses_snapshot_year():
    """Проверяет, что для каждой T строится правильный снапшот (год фильтруется)."""
    # Статьи: A (2018), B (2019), C (2019 - nk_c уже известен в графе <= 2019).
    # Будущая статья D (2021) повторно упоминает nk_c -> distance достижим.
    articles = {
        "A": (2018, ["nk_a"]),
        "B": (2019, ["nk_b"]),
        "C": (2019, ["nk_c"]),
    }
    edges = [("A", "B"), ("B", "C")]

    snap_2019 = _make_snapshot(2019, articles, edges)
    # Все статьи <= 2019 -> снапшот полный.

    predictor = FakePredictor(candidates=["nk_c", "nk_x", "nk_y"])

    cfg = BacktestConfig(
        start_year=2019, end_year=2019, step=1, horizon=3,
        k=3, min_distance=1, ratio=1.0, max_source_per_year=10,
    )
    bt = Backtester(predictor, cfg)

    def snapshot_factory(year: int) -> TemporalSnapshot:
        return snap_2019

    def real_future_getter(snapshot: TemporalSnapshot, real_year: int):
        # Будущая статья D (2021) содержит nk_c
        return {"D": 2021}, {"D": {"nk_c"}}

    def source_getter(snapshot: TemporalSnapshot, limit: int):
        return [("A", "nk_a")]  # из снапшота

    results = bt.run(snapshot_factory, real_future_getter, source_getter)
    yr = results[0]
    # nk_c в top3 -> hit, distance nk_a -> nk_c = 2 (A->B->C по цитированию)
    assert yr.n_cases == 1
    assert yr.snapshot_size == 3
    assert yr.distance_stats["count"] == 1
    assert yr.distance_stats["mean"] == 2.0
    assert abs(yr.kpi1_avg["mrr"] - 1.0) < 1e-9


def test_empty_source_no_results():
    """Пустой список источников -> корректный пустой YearResult."""
    snap = _make_snapshot(2020, {"A": (2018, ["nk_a"])}, [])
    predictor = FakePredictor(candidates=["nk_a"])

    bt = Backtester(predictor, BacktestConfig(
        start_year=2020, end_year=2020, step=1, horizon=2, k=5,
        min_distance=1, ratio=1.0, max_source_per_year=10,
    ))

    def snapshot_factory(year: int):
        return snap

    def real_future_getter(snapshot: TemporalSnapshot, real_year: int):
        return {}, {}

    def source_getter(snapshot: TemporalSnapshot, limit: int):
        return []

    results = bt.run(snapshot_factory, real_future_getter, source_getter)
    yr = results[0]
    assert yr.n_cases == 0
    assert yr.distance_stats["count"] == 0
    assert yr.kpi1_avg["precision@5"] == 0.0


if __name__ == "__main__":
    test_backtest_kpi1_and_kpi2_work()
    test_backtest_multiple_years_uses_snapshot_year()
    test_empty_source_no_results()
    print("All integration tests passed.")
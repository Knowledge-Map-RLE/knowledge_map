"""
Domain — метрики двух KPI.

KPI-1 (Predictive Accuracy): Precision@K, Recall@K, F1@K, MRR, Hits@K.
KPI-2 (Predictive Distance): mean/median/max/P90 + Long-range Recall@K(d >= D).

Все метрики принимают ТОЛЬКО стандартные структуры данных (списки, словари) —
никаких Neo4j-зависимостей. Это делает их легко тестируемыми и переиспользуемыми.
"""
from __future__ import annotations

import statistics
from typing import Dict, Iterable, List, Optional, Sequence

# ─── KPI-1: Ranking-метрики точности предсказания ────────────────────────── #

def precision_at_k(predicted: List[str], relevant: Iterable[str], k: int) -> float:
    """Доля верных среди top-K предсказанных утверждений."""
    if k <= 0:
        return 0.0
    relevant_set = set(relevant)
    top_k = predicted[:k]
    if not top_k:
        return 0.0
    hits = sum(1 for nk in top_k if nk in relevant_set)
    return hits / len(top_k)


def recall_at_k(predicted: List[str], relevant: Sequence[str], k: int) -> float:
    """Доля реальных будущих утверждений, попавших в top-K."""
    relevant_set = set(relevant)
    if not relevant_set:
        return 0.0
    top_k_set = set(predicted[:k])
    hits = top_k_set & relevant_set
    return len(hits) / len(relevant_set)


def f1_at_k(predicted: List[str], relevant: Sequence[str], k: int) -> float:
    """Гармоническое среднее Precision@K и Recall@K."""
    p = precision_at_k(predicted, relevant, k)
    r = recall_at_k(predicted, relevant, k)
    if p + r == 0:
        return 0.0
    return 2 * p * r / (p + r)


def mrr(predicted: List[str], relevant: Iterable[str]) -> float:
    """Mean Reciprocal Rank: 1 / ранг первой верной среди всех предсказанных."""
    relevant_set = set(relevant)
    for i, nk in enumerate(predicted, start=1):
        if nk in relevant_set:
            return 1.0 / i
    return 0.0


def hits_at_k(predicted: List[str], relevant: Iterable[str], k: int) -> int:
    """Число верных предсказаний в top-K (0..k)."""
    relevant_set = set(relevant)
    return sum(1 for nk in predicted[:k] if nk in relevant_set)


def ranking_metrics(predicted: List[str], relevant: Sequence[str], k: int) -> Dict[str, float]:
    """Сводный набор KPI-1 метрик для одного тестового случая."""
    return {
        "precision@{k}".format(k=k): precision_at_k(predicted, relevant, k),
        "recall@{k}".format(k=k): recall_at_k(predicted, relevant, k),
        "f1@{k}".format(k=k): f1_at_k(predicted, relevant, k),
        "mrr": mrr(predicted, relevant),
        "hits@{k}".format(k=k): float(hits_at_k(predicted, relevant, k)),
    }


# ─── KPI-2: Статистика расстояний ────────────────────────────────────────── #

def distance_stats(distances: Sequence[int]) -> Dict[str, float]:
    """mean/median/max/P90 по списку графовых расстояний успешных предсказаний."""
    if not distances:
        return {"mean": 0.0, "median": 0.0, "max": 0.0, "p90": 0.0, "count": 0}

    sorted_d = sorted(int(d) for d in distances)
    n = len(sorted_d)
    p90_idx = max(0, min(n - 1, int(0.9 * n)))

    return {
        "mean": statistics.mean(sorted_d),
        "median": statistics.median(sorted_d),
        "max": float(sorted_d[-1]),
        "p90": float(sorted_d[p90_idx]),
        "count": n,
    }


def longrange_recall_at_k(
    predicted: List[str],
    relevant: Sequence[str],
    distances: Dict[str, Optional[int]],
    min_distance: int,
    k: int,
) -> float:
    """Доля реальных будущих утверждений, находящихся на расстоянии >= min_distance,
    которые система предсказала в top-K.

    Это основной показатель KPI-2 из документа:
    "Какой процент будущих истинных утверждений, находящихся минимум в D hops
     от исходной статьи, система смогла предсказать в top-K?"

    Args:
        predicted: ранжированный список предсказанных norm_key.
        relevant:  реальные будущие norm_key (эталон).
        distances: {norm_key: расстояние до исходной статьи} на snapshot(T).
        min_distance: порог D (включительно).
        k: топ-K.

    Returns:
        доля дальних релевантных утверждений, попавших в top-K.
    """
    far_relevant = [
        nk
        for nk in relevant
        if (d := distances.get(nk)) is not None and d >= min_distance
    ]
    if not far_relevant:
        return 0.0

    top_k_set = set(predicted[:k])
    far_hits = [nk for nk in far_relevant if nk in top_k_set]
    return len(far_hits) / len(far_relevant)


# ─── Агрегация ───────────────────────────────────────────────────────────── #

def aggregate_ranking_metrics(per_case: List[Dict[str, float]]) -> Dict[str, float]:
    """Усредняет ranking-метрики по всем тестовым случаям (всем контрольным точкам T)."""
    if not per_case:
        keys = ["precision", "recall", "f1", "mrr", "hits"]
        return {k: 0.0 for k in keys}

    keys = list(per_case[0].keys())
    out: Dict[str, float] = {}
    for key in keys:
        values = [case[key] for case in per_case if key in case]
        out[key] = statistics.mean(values) if values else 0.0
    return out

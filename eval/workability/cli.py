"""
CLI — точка входа для проверки работоспособности Карты Знаний по двум KPI.

Запуск (из окружения api/):

    cd d:\\Knowledge_Map\\api
    poetry run python ..\\eval\\workability\\cli.py [options]

Примеры:
    # Смоук-тест на ограниченной выборке статей
    poetry run python ..\\eval\\workability\\cli.py --limit-docs 200 --start-year 2015 --end-year 2020

    # Полный прогон
    poetry run python ..\\eval\\workability\\cli.py --start-year 2010 --end-year 2025

Результаты: Markdown-отчёт + JSON (в eval/reports/workability/).
"""
from __future__ import annotations

import argparse
import datetime
import json
import logging
import random
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

API_DIR = Path(__file__).resolve().parent.parent.parent / "api"
EVAL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(API_DIR))
sys.path.insert(0, str(EVAL_DIR))

from neomodel import config as neomodel_config  # noqa: E402
from neomodel import db  # noqa: E402

from workability.application.backtest import Backtester, BacktestConfig  # noqa: E402
from workability.domain.baseline import RandomBaseline  # noqa: E402
from workability.domain.distances import build_doc_adjacency  # noqa: E402
from workability.domain.statements import CanonicalStatement, Article, TemporalSnapshot  # noqa: E402
from workability.infrastructure.neo4j_loader import Neo4jLoader  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("workability.cli")

NEO4J_URL = "bolt://neo4j:password@127.0.0.1:7687"
REPORT_DIR = Path(__file__).resolve().parent.parent / "reports" / "workability"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Workability check for Knowledge Map.")
    p.add_argument("--start-year", type=int, default=2010)
    p.add_argument("--end-year", type=int, default=2025)
    p.add_argument("--step", type=int, default=1)
    p.add_argument("--horizon", type=int, default=5,
                   help="Размер окна будущего (T, T+H] лет для эталона.")
    p.add_argument("--k", type=int, default=10)
    p.add_argument("--min-distance", type=int, default=10,
                   help="Порог D для Long-range Recall@K(d>=D).")
    p.add_argument("--ratio", type=float, default=0.05,
                   help="Доля статей <= T, берём как источники прогноза.")
    p.add_argument("--max-source-per-year", type=int, default=2000,
                   help="Максимум source-утверждений на контрольную точку.")
    p.add_argument("--limit-docs", type=int, default=None,
                   help="Ограничить число статей (для быстрого смоук-теста).")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--output-dir", type=Path, default=REPORT_DIR)
    p.add_argument("--predictor", type=str, default="random",
                   choices=["random"],
                   help="Предиктор (пока только baseline random).")
    return p.parse_args()


def build_stdout_summary(results, args) -> str:
    """Краткая сводка по всем контрольным точкам."""
    lines = []
    for yr in results:
        lines.append(
            f"T={yr.year}: cases={yr.n_cases} snapshot_articles={yr.snapshot_size} "
            f"P@{args.k}={yr.kpi1_avg.get(f'precision@{args.k}', 0):.3f} "
            f"R@{args.k}={yr.kpi1_avg.get(f'recall@{args.k}', 0):.3f} "
            f"MRR={yr.kpi1_avg.get('mrr', 0):.3f} "
            f"dist_mean={yr.distance_stats.get('mean', 0):.2f} "
            f"LR_Recall={yr.longrange_recall:.3f}"
        )
    return "\n".join(lines)


class Corpus:
    """Полный корпус: article_years, statements, edges — в памяти.

    Даёт возможность snapshot() фильтровать ≤ T, а реальному эталону (будущему)
    — знать statements статей > T.
    """

    def __init__(
        self,
        article_years: Dict[str, int],
        statements: List[CanonicalStatement],
        edges: Set[Tuple[str, str]],
    ) -> None:
        self.article_years = article_years
        self.statements = statements
        self.edges = edges
        # doc_id -> list[norm_key]
        self.doc_stmts: Dict[str, List[str]] = {}
        for st in statements:
            if st.doc_id:
                self.doc_stmts.setdefault(st.doc_id, []).append(st.norm_key)


class CLIRunner:
    """Оркестрация данных И backtest из CLI."""

    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.loader = Neo4jLoader(NEO4J_URL)
        random.seed(args.seed)

    # ─── Загрузка данных ─────────────────────────────────────────────── #

    def load_corpus(self) -> Corpus:
        logger.info("Loading article publication years…")
        if self.args.limit_docs:
            doc_ids = self.loader.load_statement_doc_ids(limit=self.args.limit_docs)
            logger.info("  %d documents with statements", len(doc_ids))
            if not doc_ids:
                logger.error(
                    "В базе нет статей с утверждениями (Action.doc_id) — "
                    "механизм проверки не может построить ни одного case. "
                    "Загрузите обработанные статьи с утверждениями."
                )
                raise SystemExit(2)
            article_years = self.loader.load_article_years(doc_ids=doc_ids)
        else:
            article_years = self.loader.load_article_years()
        logger.info("  %d documents with publication date", len(article_years))

        if not article_years:
            logger.warning(
                "В базе нет документов с publication_date — временной split невозможен. "
                "Механизм проверки требует статей с датой публикации. "
                "Загрузите статьи с метаданными (publication_date)."
            )
            return Corpus(article_years={}, statements=[], edges=set())
        else:
            doc_ids = None

        logger.info("Loading statements (Action norm_keys)…")
        statements = self.loader.load_statements(doc_ids=doc_ids)
        logger.info("  %d canonical statements loaded", len(statements))

        logger.info("Loading BIBLIOGRAPHIC_LINK edges…")
        edges = self.loader.load_bibliographic_edges(doc_ids=doc_ids)
        logger.info("  %d bibliographic edges loaded", len(edges))

        return Corpus(article_years, statements, edges)

    # ─── Фабрики для backtester ─────────────────────────────────────── #

    def snapshot_factory(self, corpus: Corpus):
        """Собирает TemporalSnapshot для контрольной точки T (статьи ≤ T)."""
        def build(year: int) -> TemporalSnapshot:
            return self.loader.build_snapshot(
                year, corpus.article_years, corpus.statements, corpus.edges
            )
        return build

    def real_future_getter(self, corpus: Corpus):
        """Возвращает реальные будущие статьи в окне (T, T+H].

        Фильтрует по doc_id из corpus.article_years:
          future если year ∈ (snapshot_year, T+horizon].
        Statements берём из corpus.doc_stmts.
        """
        def getter(snapshot: TemporalSnapshot, real_year: int):
            future_articles: Dict[str, Set[str]] = {}
            year_map: Dict[str, int] = {}
            for doc_id, y in corpus.article_years.items():
                if snapshot.year < y <= real_year:
                    nks = set(corpus.doc_stmts.get(doc_id, []))
                    if nks:
                        future_articles[doc_id] = nks
                        year_map[doc_id] = y
            return year_map, future_articles

        return getter

    def source_getter(self, corpus: Corpus):
        """Выбирает source-утверждения из snapshot(T) для прогноза."""
        def getter(snapshot: TemporalSnapshot, limit: int):
            sources: List[Tuple[str, str]] = []
            doc_ids = sorted(snapshot.articles.keys())
            if limit and len(doc_ids) > limit:
                doc_ids = random.sample(doc_ids, limit)
            for doc_id in doc_ids:
                art = snapshot.articles[doc_id]
                if art.statements:
                    src_nk = sorted(art.statements)[0]
                    sources.append((doc_id, src_nk))
            return sources

        return getter

    def run(self) -> List:
        cfg = BacktestConfig(
            start_year=self.args.start_year,
            end_year=self.args.end_year,
            step=self.args.step,
            horizon=self.args.horizon,
            k=self.args.k,
            min_distance=self.args.min_distance,
            ratio=self.args.ratio,
            max_source_per_year=self.args.max_source_per_year,
        )

        corpus = self.load_corpus()
        predictor = RandomBaseline(seed=self.args.seed)

        bt = Backtester(predictor, cfg)
        results = bt.run(
            snapshot_factory=self.snapshot_factory(corpus),
            real_future_getter=self.real_future_getter(corpus),
            source_getter=self.source_getter(corpus),
        )
        return results


def generate_markdown_report(results, args, meta: dict) -> str:
    lines = [
        "# Проверка работоспособности Карты Знаний (два KPI)",
        "",
        "## Метаданные прогона",
        "",
        f"- Дата: {meta['ts']}",
        f"- Контрольные точки: {args.start_year}–{args.end_year} (шаг {args.step} лет)",
        f"- Горизонт прогноза H: {args.horizon} лет",
        f"- Top-K: {args.k}",
        f"- Порог дальности D: {args.min_distance}",
        f"- Предиктор: random (baseline)",
        "",
        "## Результаты по контрольным точкам T",
        "",
        "| T | Cases | Snapshot | P@K | R@K | F1@K | MRR | Hits@K | Dist mean | Dist max | LR_Recall@K(d≥D) |",
        "|---|-------|----------|-----|-----|------|-----|--------|-----------|----------|-------------------|",
    ]

    for yr in results:
        lines.append(
            f"| {yr.year} | {yr.n_cases} | {yr.snapshot_size} "
            f"| {yr.kpi1_avg.get(f'precision@{args.k}', 0):.4f} "
            f"| {yr.kpi1_avg.get(f'recall@{args.k}', 0):.4f} "
            f"| {yr.kpi1_avg.get(f'f1@{args.k}', 0):.4f} "
            f"| {yr.kpi1_avg.get('mrr', 0):.4f} "
            f"| {yr.kpi1_avg.get(f'hits@{args.k}', 0):.2f} "
            f"| {yr.distance_stats.get('mean', 0):.2f} "
            f"| {yr.distance_stats.get('max', 0):.2f} "
            f"| {yr.longrange_recall:.4f} |"
        )
    return "\n".join(lines)


def save_json(results, meta, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "meta": meta,
        "years": [
            {
                "year": r.year,
                "n_cases": r.n_cases,
                "snapshot_size": r.snapshot_size,
                "kpi1_avg": r.kpi1_avg,
                "distance_stats": r.distance_stats,
                "longrange_recall": r.longrange_recall,
            }
            for r in results
        ],
    }
    fname = output_dir / f"workability_{meta['ts'].replace(' ', '_').replace(':', '')}.json"
    fname.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return fname


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    runner = CLIRunner(args)
    results = runner.run()

    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    meta = {
        "ts": ts,
        "predictor": args.predictor,
        "start_year": args.start_year,
        "end_year": args.end_year,
        "step": args.step,
        "horizon": args.horizon,
        "k": args.k,
        "min_distance": args.min_distance,
        "limit_docs": args.limit_docs,
    }

    print("\n" + "=" * 60)
    print("  WORKABILITY BACKTEST SUMMARY")
    print("=" * 60)
    print(build_stdout_summary(results, args))
    print("=" * 60)

    report_path = args.output_dir / f"workability_report_{ts.replace(' ', '_').replace(':', '')}.md"
    report_path.write_text(
        generate_markdown_report(results, args, meta), encoding="utf-8"
    )
    json_path = save_json(results, meta, args.output_dir)

    print(f"\nReport:  {report_path}")
    print(f"JSON:    {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
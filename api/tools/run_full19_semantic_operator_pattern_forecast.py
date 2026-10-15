"""Проверяет перенос семантических операторных форм с удержанием прямых цитаторов."""
from __future__ import annotations

import argparse
import json
import logging
import random
import sys
from collections import Counter
from hashlib import sha256
from pathlib import Path
from time import perf_counter

from domain.article_maps import fingerprint, require
from domain.comparison_normalization import VERSION as NORMALIZER_VERSION
from domain.operator_frame_routing import DICTIONARY_SHA256, VERSION as ROUTING_VERSION
from domain.operator_pattern_forecast import (
    VERSION as FORECAST_VERSION,
    _permuted_author_groups,
    _semantic_pairs,
    _single_author_groups,
    evaluate,
    forecast_from_rows,
    validate_map_snapshot,
)
from tools.run_full19_transition_pattern_forecast import (
    _article_citation_keys,
    _citation_matches,
)


ROOT = Path(r"D:\Knowledge_Map")
DEFAULT_MANIFEST = ROOT / (
    "eval/whole_map_forecast/semantic-parts-v1/"
    "full-corpus-19-prepared-v1/source-manifest.json"
)
LIMIT = 20
MIN_SUPPORT = 2
PERMUTATION_SEEDS = tuple(range(100))
VERSION = "full19-semantic-operator-pattern-citation-holdout-v1"


def _digest(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def _disable_network(event: str, values: tuple) -> None:
    if event in {"socket.connect", "socket.connect_ex", "socket.getaddrinfo", "socket.bind"}:
        raise RuntimeError("Сетевой доступ запрещён для офлайн-эксперимента")


def _load(manifest_path: Path) -> tuple[dict[str, dict], dict, bytes]:
    raw_manifest = manifest_path.read_bytes()
    manifest = json.loads(raw_manifest.decode("utf-8"))
    require(len(manifest.get("sources", [])) == 19, "Ожидались ровно 19 карт")
    maps: dict[str, dict] = {}
    meta: dict[str, dict] = {}
    for entry in manifest["sources"]:
        raw = Path(entry["path"]).read_bytes()
        require(_digest(raw) == entry["file_sha256"], "Хеш карты не совпал с манифестом")
        article = json.loads(raw.decode("utf-8"))
        article_id = article["article_id"]
        require(article_id == entry["reference"]["article_id"], "ID карты не совпал")
        require(article_id not in maps, "Статья повторяется в манифесте")
        require(fingerprint(article["graph"]) == entry["graph_sha256"], "Хеш графа не совпал")
        validate_map_snapshot(article)
        maps[article_id] = article
        meta[article_id] = {
            "map_sha256": _digest(raw),
            "graph_sha256": entry["graph_sha256"],
            "source_sha256": entry["source_sha256"],
            "family": entry.get("family", article_id),
            "title": entry.get("title") or article.get("article_title") or article_id,
        }
    return maps, meta, raw_manifest


def _citation_exclusions(maps: dict[str, dict]) -> dict[str, list[dict]]:
    keyed = {
        article_id: {
            "citation_keys": _article_citation_keys(article, article_id),
            "source_text": article["source"]["text"],
        }
        for article_id, article in maps.items()
    }
    exclusions: dict[str, list[dict]] = {}
    for target_id, target in keyed.items():
        rows = []
        for source_id, source in keyed.items():
            if source_id == target_id:
                continue
            matches = _citation_matches(target, source)
            if matches:
                rows.append({"citing_article_id": source_id, "evidence": matches})
        exclusions[target_id] = rows
    return exclusions


def _score_prediction(rows: dict[str, list[dict]], target_id: str, target: dict,
                      training_ids: list[str], mode: str) -> dict:
    forecast = forecast_from_rows(
        {source_id: rows[source_id] for source_id in training_ids},
        mode=mode,
        limit=LIMIT,
        min_support=MIN_SUPPORT,
    )
    return {
        "forecast": forecast,
        "score": evaluate(forecast, target),
    }


def _aggregate(folds: list[dict], mode: str) -> dict:
    rows = [fold["modes"][mode]["score"] for fold in folds]
    candidates = sum(row["candidate_count"] for row in rows)
    hits = sum(row["unique_patterns_hit"] for row in rows)
    targets = sum(row["unique_operator_patterns_in_target"] for row in rows)
    instances = sum(row["target_transition_instances_hit"] for row in rows)
    return {
        "folds": len(rows),
        "candidate_count": candidates,
        "unique_target_patterns": targets,
        "unique_pattern_hits": hits,
        "target_transition_instances_hit": instances,
        "micro_precision": hits / candidates if candidates else None,
        "micro_recall": hits / targets if targets else None,
        "folds_with_at_least_one_hit": sum(row["unique_patterns_hit"] > 0 for row in rows),
        "target_exposure": "ретроспективная проверка с поочерёдным удержанием одной статьи; карты и метки были доступны при аудите",
    }


def run(manifest_path: Path, output: Path) -> dict:
    maps, metadata, manifest_raw = _load(manifest_path)
    exclusions = _citation_exclusions(maps)

    source_rows: dict[str, dict[str, list[dict]]] = {
        "graph": {},
        "semantic_without_dependencies": {},
        "permuted_dependencies": {},
    }
    diagnostics = {}
    normalized_by_source = {}
    from domain.comparison_normalization import normalize_map

    for article_id, article in sorted(maps.items()):
        source_rows["graph"][article_id] = _single_author_groups(article)
        source_rows["semantic_without_dependencies"][article_id] = _semantic_pairs(article)
        normalized_by_source[article_id] = normalize_map(article)
        diagnostics[article_id] = {
            "canonical_knowledge_count": len(article["graph"]["knowledge"]),
            "single_premise_author_groups": len(source_rows["graph"][article_id]),
            "semantic_pairs_without_edges": len(source_rows["semantic_without_dependencies"][article_id]),
        }

    folds = []
    all_modes = tuple(source_rows)
    for seed in PERMUTATION_SEEDS:
        for article_id, article in sorted(maps.items()):
            article_seed = seed + int(fingerprint(article_id)[:8], 16)
            source_rows["permuted_dependencies"].setdefault(article_id, [])
            # Перестановка сохраняет число входов, ранговые ограничения и DAG.
            permuted, stats = _permuted_author_groups(
                article, article_seed, normalized_by_source[article_id]
            )
            source_rows["permuted_dependencies"][article_id].append((permuted, stats))

    for target_id, target in sorted(maps.items()):
        excluded_ids = {row["citing_article_id"] for row in exclusions[target_id]}
        training_ids = sorted(set(maps) - {target_id} - excluded_ids)
        mode_results = {}
        for mode in ("graph", "semantic_without_dependencies"):
            mode_results[mode] = _score_prediction(
                source_rows[mode], target_id, target, training_ids, mode
            )
        permutation_results = []
        for seed in PERMUTATION_SEEDS:
            rows_by_source = {
                article_id: source_rows["permuted_dependencies"][article_id][seed][0]
                for article_id in training_ids
            }
            permuted_forecast = forecast_from_rows(
                rows_by_source,
                mode="permuted_dependencies",
                limit=LIMIT,
                min_support=MIN_SUPPORT,
            )
            permutation_results.append(evaluate(permuted_forecast, target))
        mode_results["permuted_dependencies"] = {
            "scores": permutation_results,
            "mean_hits": sum(r["unique_patterns_hit"] for r in permutation_results)
            / len(permutation_results),
            "max_hits": max(r["unique_patterns_hit"] for r in permutation_results),
            "at_least_graph_hits": sum(
                r["unique_patterns_hit"] >= mode_results["graph"]["score"]["unique_patterns_hit"]
                for r in permutation_results
            ),
            "seed_count": len(permutation_results),
        }
        folds.append({
            "target_article_id": target_id,
            "target_title": metadata[target_id]["title"],
            "target_map_sha256": metadata[target_id]["map_sha256"],
            "training_article_ids": training_ids,
            "excluded_direct_citers": exclusions[target_id],
            "mode_candidate_counts": {
                mode: mode_results[mode]["forecast"]["candidate_count_before_limit"]
                for mode in ("graph", "semantic_without_dependencies")
            },
            "modes": mode_results,
        })

    summary = {mode: _aggregate(folds, mode)
               for mode in ("graph", "semantic_without_dependencies")}
    graph_hits = [fold["modes"]["graph"]["score"]["unique_patterns_hit"] for fold in folds]
    no_edge_hits = [fold["modes"]["semantic_without_dependencies"]["score"]["unique_patterns_hit"] for fold in folds]
    permutation_at_least = sum(
        fold["modes"]["permuted_dependencies"]["at_least_graph_hits"]
        for fold in folds
    )
    permutation_total = len(folds) * len(PERMUTATION_SEEDS)
    permutation_hits_by_seed = [
        sum(
            fold["modes"]["permuted_dependencies"]["scores"][seed]["unique_patterns_hit"]
            for fold in folds
        )
        for seed in range(len(PERMUTATION_SEEDS))
    ]
    result = {
        "version": VERSION,
        "predictor_version": FORECAST_VERSION,
        "routing_version": ROUTING_VERSION,
        "routing_dictionary_sha256": DICTIONARY_SHA256,
        "normalizer_version": NORMALIZER_VERSION,
        "source_manifest_path": str(manifest_path),
        "source_manifest_sha256": _digest(manifest_raw),
        "source_count": len(maps),
        "source_map_sha256": {key: metadata[key]["map_sha256"] for key in sorted(metadata)},
        "citations_excluded": sum(len(value) for value in exclusions.values()),
        "candidate_limit_per_target": LIMIT,
        "minimum_support_publications": MIN_SUPPORT,
        "permutation_seed_count": len(PERMUTATION_SEEDS),
        "source_diagnostics": diagnostics,
        "summary": summary,
        "graph_wins": sum(a > b for a, b in zip(graph_hits, no_edge_hits)),
        "graph_losses": sum(a < b for a, b in zip(graph_hits, no_edge_hits)),
        "ties": sum(a == b for a, b in zip(graph_hits, no_edge_hits)),
        "permutation_fraction_at_least_graph": permutation_at_least / permutation_total,
        "permutation_comparisons": permutation_total,
        "permutation_total_hits_by_seed": permutation_hits_by_seed,
        "folds": folds,
        "model_calls": 0,
        "network_calls": 0,
        "scientific_claims_evaluated": False,
        "confirmatory": False,
        "interpretation_ru": (
            "Сравниваются точные формы семантических операторов, а не истинность научных фактов. "
            "Рёбра дают свидетельство преимущества только при устойчивом выигрыше над теми же "
            "знаниями без рёбер и переставленными связями."
        ),
    }
    output.mkdir(parents=True, exist_ok=False)
    raw = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
    (output / "data.json").write_bytes(raw)
    (output / "implementation.py").write_bytes(Path(__file__).read_bytes())
    (output / "source-manifest.json").write_bytes(manifest_raw)
    (output / "report.ru.md").write_text(render_report(result), encoding="utf-8")
    result["output_data_sha256"] = _digest(raw)
    (output / "verification.json").write_text(
        json.dumps({
            "data_sha256": result["output_data_sha256"],
            "implementation_sha256": _digest(Path(__file__).read_bytes()),
            "manifest_sha256": result["source_manifest_sha256"],
            "model_calls": 0,
            "network_calls": 0,
            "target_used_for_training": False,
            "direct_citers_excluded_per_fold": True,
            "all_maps_schema6_and_dag_valid": True,
            "permutation_controls": len(PERMUTATION_SEEDS),
        }, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    return result


def render_report(data: dict) -> str:
    graph, baseline = data["summary"]["graph"], data["summary"]["semantic_without_dependencies"]
    permutation_totals = data.get("permutation_total_hits_by_seed")
    if permutation_totals is None:
        permutation_totals = [
            sum(
                fold["modes"]["permuted_dependencies"]["scores"][seed]["unique_patterns_hit"]
                for fold in data["folds"]
            )
            for seed in range(data["permutation_seed_count"])
        ]
    permutation_mean = sum(permutation_totals) / len(permutation_totals)
    lines = [
        "# Семантические формы операторов: проверка на 19 картах",
        "",
        "**Это проверка формы авторских переходов, не прогноз истинности научных утверждений.** В каждом фолде целевая карта и найденные прямые цитаторы исключены из обучения. Для кандидата требуется повтор в двух публикациях; лимит — 20 форм на статью.",
        "",
        f"Вход: {data['source_count']} карт схемы 6. Исключено пар «цель — прямой цитатор»: {data['citations_excluded']}. Модельных и сетевых вызовов: 0. Перестановочных контролей: {data['permutation_comparisons']}.",
        "",
        "Профиль формы сохраняет вид блока, семейство предиката, роли, статус действия, логику блока, отрицание и модальность. Сам графовый режим обучается на одно-предпосылочных группах рёбер. Контроль без связей строит пары по общим семантическим участникам. Перестановочный контроль сохраняет число входов и ранговую ацикличность, заменяя исходные предпосылки.",
        "",
        "## Сводка при общем предельном лимите",
        "",
        "| Режим | Кандидатов | Совпавшие формы | Полнота | Цели с попаданием |",
        "|---|---:|---:|---:|---:|",
        f"| Исходные зависимости | {graph['candidate_count']} | {graph['unique_pattern_hits']} | {graph['micro_recall']:.3f} | {graph['folds_with_at_least_one_hit']}/{graph['folds']} |",
        f"| Общие участники, без рёбер | {baseline['candidate_count']} | {baseline['unique_pattern_hits']} | {baseline['micro_recall']:.3f} | {baseline['folds_with_at_least_one_hit']}/{baseline['folds']} |",
        f"| Рёбра выигрывают / проигрывают / ничья | {data['graph_wins']} / {data['graph_losses']} / {data['ties']} |",
        "",
        f"Лимит одинаков для режимов — до {LIMIT} кандидатов в каждом удержанном фолде. Фактическое число меньше, если поддержка отсеяла остальные формы. Поддержка считается по публикациям и не доказывает независимость когорт.",
        "",
        "## Перестановочный контроль",
        "",
        f"В {len(permutation_totals)} наборах с переставленными связями получено от {min(permutation_totals)} до {max(permutation_totals)} совпавших форм за весь корпус; среднее — {permutation_mean:.2f}. Исходный граф и контроль без рёбер дали по {graph['unique_pattern_hits']} и {baseline['unique_pattern_hits']} совпадений. Когда все режимы дают ноль, доля перестановок «не хуже графа» не является свидетельством: сравнение не обнаружило положительного сигнала.",
        "",
        "## Границы вывода",
        "",
        "Совпадение операторной формы не означает, что совпало содержание результата, причинность или условия применимости. Публикации могли использовать одну и ту же когорту; число статей не равно числу независимых исследований. Это ретроспективная проверка с поочерёдным удержанием одной статьи: контрольные карты уже были доступны в процессе предыдущего аудита, поэтому статистика не является подтверждающей оценкой.",
        "",
        "Преимущество Карты Знаний можно признать только для этой структурно-семантической задачи, если исходные рёбра стабильно превосходят оба контроля. Для главной цели — прогноза новых научных знаний — отдельно нужны кандидаты с заполненными предикатами, участниками, числами и контекстом, а также заранее удержанные независимые источники.",
        "",
        f"Манифест SHA-256: `{data['source_manifest_sha256']}`. Словарь операторов: `{data['routing_dictionary_sha256']}`. Результат — диагностика, экспертная проверка не проводилась.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--render-existing", type=Path,
                        help="Пересобрать только русский отчёт из уже сохранённого data.json")
    args = parser.parse_args()
    sys.addaudithook(_disable_network)
    logging.basicConfig(level=logging.INFO)
    started = perf_counter()
    if args.render_existing:
        result = json.loads(args.render_existing.read_text(encoding="utf-8"))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(render_report(result), encoding="utf-8")
    else:
        result = run(args.manifest, args.output)
    logging.info("semantic_operator_pattern_forecast duration_seconds=%.3f", perf_counter() - started)
    print(json.dumps({
        "output": str(args.output),
        "graph": result["summary"]["graph"],
        "without_edges": result["summary"]["semantic_without_dependencies"],
        "graph_wins": result["graph_wins"],
        "graph_losses": result["graph_losses"],
        "ties": result["ties"],
        "permutation_fraction_at_least_graph": result["permutation_fraction_at_least_graph"],
        "model_calls": 0,
        "network_calls": 0,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()

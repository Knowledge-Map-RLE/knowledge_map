"""Проверяет, превосходит ли направленность переходов случайное связывание типов."""
from __future__ import annotations

import json
import logging
import random
from hashlib import sha256
from pathlib import Path

from domain.article_maps import fingerprint, require
from domain.cohort_operation_result_transfer import extract_map as extract_result_map
from domain.cohort_operation_transfer import forecast_for_known_operations, score
from infrastructure.immutable_files import write_immutable
from tools import run_full19_cohort_result_usage_diagnostic as base
from tools.run_free_prediction import disable_network


ROOT = Path(r"D:\Knowledge_Map")
OUTPUT = ROOT / (
    "eval/whole_map_forecast/cohort_operation_prediction/"
    "full19-result-usage-permutation-v1"
)
VERSION = "full19-cohort-result-usage-permutation-1"
PERMUTATION_COUNT = 1000
MODES = ("dependency_edges_all_usage", "dependency_edges_result_usage")
MODE_RU = {
    "dependency_edges_all_usage": "Все прямые связи",
    "dependency_edges_result_usage": "Только связи с меткой `result`",
}


def _sha(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def _json_bytes(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")


def _randomize_links(row: dict, seed: int) -> tuple[dict, bool]:
    """Перемешивает пару, сохраняя число рёбер и словарь концов статьи."""
    result = dict(row)
    operations = sorted(set(row["operator_families"]))
    outputs = sorted(set(row["output_families"]))
    original = {tuple(pair) for pair in row["graph_links"]}
    possible = [(operation, output) for operation in operations for output in outputs]
    if not original or len(possible) <= len(original):
        return {**result, "graph_links": [list(pair) for pair in sorted(original)]}, False
    rng = random.Random(seed)
    shuffled = set(rng.sample(possible, len(original)))
    result["graph_links"] = [list(pair) for pair in sorted(shuffled)]
    return result, shuffled != original


def _lopo_permutation(
    rows: dict[str, dict],
    truth_by_article: dict[str, set[tuple[str, str]]],
    strict_rows_by_article: dict[str, dict],
    seed: int,
) -> dict:
    randomized_all, randomized_result, changed = {}, {}, {}
    for source_id, row in rows.items():
        stable_seed = int(fingerprint([seed, source_id])[:8], 16)
        randomized_all[source_id], changed_all = _randomize_links(row, stable_seed)
        strict = strict_rows_by_article[source_id]
        randomized_result[source_id], changed_result = _randomize_links(strict, stable_seed ^ 0xA5A5A5A5)
        changed[source_id] = {"all_usage": changed_all, "result_usage": changed_result}

    aggregate = {
        mode: {"predicted": 0, "target": 0, "hits": 0}
        for mode in MODES
    }
    changed_training_maps = {mode: 0 for mode in MODES}
    eligible_targets = 0
    for target_id in sorted(rows):
        target_row = rows[target_id]
        truth = truth_by_article[target_id]
        if not truth:
            continue
        eligible_targets += 1
        training_all = {key: value for key, value in randomized_all.items() if key != target_id}
        training_result = {key: value for key, value in randomized_result.items() if key != target_id}
        predictions = {
            "dependency_edges_all_usage": forecast_for_known_operations(
                training_all, set(target_row["operator_families"]), base.MINIMUM_SUPPORT
            )["dependency_edges"],
            "dependency_edges_result_usage": forecast_for_known_operations(
                training_result, set(target_row["operator_families"]), base.MINIMUM_SUPPORT
            )["dependency_edges"],
        }
        for mode, raw_pairs in predictions.items():
            candidates = {tuple(pair) for pair in raw_pairs}
            scored = score(candidates, truth)
            aggregate[mode]["predicted"] += scored["predicted_count"]
            aggregate[mode]["target"] += scored["target_count"]
            aggregate[mode]["hits"] += scored["hits"]
            key = "all_usage" if mode == "dependency_edges_all_usage" else "result_usage"
            changed_training_maps[mode] += sum(
                changed[source_id][key] for source_id in training_all
            )
    return {
        "seed": seed,
        "eligible_target_count": eligible_targets,
        "modes": aggregate,
        "changed_training_map_count_across_folds": changed_training_maps,
    }


def _distribution(observed: dict, permutations: list[dict]) -> dict:
    result = {}
    for mode in MODES:
        observed_hits = observed[mode]["hits"]
        hit_values = [item["modes"][mode]["hits"] for item in permutations]
        prediction_values = [item["modes"][mode]["predicted"] for item in permutations]
        greater_equal = sum(value >= observed_hits for value in hit_values)
        result[mode] = {
            "observed": observed[mode],
            "permutation_mean_hits": sum(hit_values) / len(hit_values),
            "permutation_min_hits": min(hit_values),
            "permutation_max_hits": max(hit_values),
            "permutation_mean_predictions": sum(prediction_values) / len(prediction_values),
            "permutations_with_hits_at_least_observed": greater_equal,
            "empirical_p_one_sided": (greater_equal + 1) / (len(hit_values) + 1),
        }
    return result


def _render_ru(result: dict) -> str:
    lines = [
        "# Перестановочный контроль переходов «операция → результат» на 19 картах",
        "",
        "**Проверяется структурный сигнал для категории результата, а не прогноз научного факта.**",
        "Для каждой удержанной карты используются только её известные операции; её выходы и связи доступны лишь оценщику. Целевая PMC10000452 исключена из корпуса по хешу исходного текста.",
        "",
        f"Проведено {PERMUTATION_COUNT} перестановок по каждому режиму на {result['source_count']} картах. Поддержка — не менее {base.MINIMUM_SUPPORT} публикаций. Оценены только карты с явными целевыми `usage=result` связями: {result['eligible_target_count']}.",
        "",
        "## Наблюдаемые и переставленные результаты",
        "",
        "| Режим | Наблюдалось: совпадения / прогнозы | Среднее совпадений в перестановках | Диапазон совпадений | Доля перестановок с не меньшим числом совпадений |",
        "|---|---:|---:|---:|---:|",
    ]
    for mode in MODES:
        row = result["permutation_summary"][mode]
        observed = row["observed"]
        lines.append(
            f"| {MODE_RU[mode]} | {observed['hits']}/{observed['predicted']} | "
            f"{row['permutation_mean_hits']:.3f} | "
            f"{row['permutation_min_hits']}–{row['permutation_max_hits']} | "
            f"{row['permutations_with_hits_at_least_observed']}/{PERMUTATION_COUNT} "
            f"(эмпирическое p={row['empirical_p_one_sided']:.3f}) |"
        )
    lines.extend([
        "",
        "## Что сохранял контроль",
        "",
        "Внутри каждой обучающей статьи сохранялись список типов операций, список типов результата и число различных пар. Менялись только соответствия между типом операции и типом результата. Поддержка по публикациям и известные методы целевой карты оставались такими же, как в исходном тесте.",
        "",
        "Перестановка не доказывает причинный смысл рёбер. Она проверяет, содержит ли их конкретное связывание больше сигнала, чем случайное соответствие тех же типов. Поддержка публикациями не подтверждает независимость когорт.",
        "",
        "## Ограничения",
        "",
        "Только три цели имеют явные метки `usage=result`; это маленькая ретроспективная выборка. Если случайное связывание часто даёт столько же совпадений, наблюдаемое преимущество может объясняться небольшим пространством категорий. Даже редкий результат в перестановках остаётся успехом классификации типа результата, а не свободным прогнозом содержания статьи.",
        "",
        "Модельных вызовов — 0; сеть отключена; исходные карты и предыдущие артефакты не изменены; экспертная научная проверка не проводилась.",
        "",
    ])
    return "\n".join(lines)


def run() -> Path:
    disable_network()
    source_manifest, source_rows, extracted = base._read_sources()
    base._SNAPSHOTS = {
        row["article_id"]: json.loads(Path(row["map_path"]).read_text(encoding="utf-8"))
        for row in source_rows
    }
    # Разбираем и валидируем исходные карты один раз, а не на каждой перестановке.
    strict_rows_by_article = {
        article_id: extract_result_map(snapshot)
        for article_id, snapshot in base._SNAPSHOTS.items()
    }
    truth_by_article = {
        article_id: {tuple(pair) for pair in row["graph_links"]}
        for article_id, row in strict_rows_by_article.items()
    }
    observed_folds = base._lopo(extracted)
    observed_aggregate = base._aggregate(observed_folds)
    observed = {
        mode: observed_aggregate["modes"][mode]
        for mode in MODES
    }
    permutations = [
        _lopo_permutation(extracted, truth_by_article, strict_rows_by_article, seed)
        for seed in range(PERMUTATION_COUNT)
    ]
    require(all(item["eligible_target_count"] == observed_aggregate["eligible_target_count"]
                for item in permutations), "Перестановка изменила список оцениваемых целей")
    permutation_summary = _distribution(observed, permutations)
    implementation_paths = [
        ROOT / "api/tools/run_full19_cohort_result_usage_diagnostic.py",
        ROOT / "api/tools/run_full19_cohort_result_usage_permutation.py",
        ROOT / "api/domain/cohort_operation_transfer.py",
        ROOT / "api/domain/cohort_operation_result_transfer.py",
        ROOT / "api/domain/operator_frame_routing.py",
    ]
    implementation = {str(path.relative_to(ROOT)): _sha(path.read_bytes()) for path in implementation_paths}
    result = {
        "version": VERSION,
        "source_manifest_sha256": _sha(base.BASE_MANIFEST.read_bytes()),
        "source_count": len(source_rows),
        "sources": source_rows,
        "eligible_target_count": observed_aggregate["eligible_target_count"],
        "minimum_publication_support": base.MINIMUM_SUPPORT,
        "permutation_count": PERMUTATION_COUNT,
        "permutation_policy": "Within each training article preserve the operation inventory, output inventory, and distinct edge count; sample new operation-output pairs uniformly without replacement.",
        "observed_target_folds": observed_folds,
        "permutation_summary": permutation_summary,
        "permutations": permutations,
        "implementation_sha256": implementation,
        "target_source_sha256_excluded": base.TARGET_SOURCE_SHA256,
        "network_disabled": True,
        "external_llm_calls": 0,
        "local_llm_calls": 0,
        "embedding_calls": 0,
        "expert_validated": False,
    }
    run_id = fingerprint({
        "version": VERSION,
        "source_manifest_sha256": result["source_manifest_sha256"],
        "implementation_sha256": implementation,
        "permutation_count": PERMUTATION_COUNT,
        "minimum_publication_support": base.MINIMUM_SUPPORT,
    })
    result["run_id"] = run_id
    files = {
        "data.json": _json_bytes(result),
        "report.ru.md": _render_ru(result).encode("utf-8"),
    }
    verification = {
        "run_id": run_id,
        "files_sha256": {name: _sha(raw) for name, raw in files.items()},
        "source_count": len(source_rows),
        "eligible_target_count": result["eligible_target_count"],
        "permutation_count": PERMUTATION_COUNT,
        "target_source_excluded_by_sha256": True,
        "network_disabled": True,
        "model_calls": 0,
        "expert_validated": False,
    }
    files["verification.json"] = _json_bytes(verification)
    output = OUTPUT / "runs" / run_id
    output.mkdir(parents=True, exist_ok=True)
    for name, raw in files.items():
        write_immutable(output / name, raw)
    logging.info("full19_result_permutation_complete run=%s perms=%d eligible=%d",
                 run_id, PERMUTATION_COUNT, result["eligible_target_count"])
    return output


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    print(run())


if __name__ == "__main__":
    main()

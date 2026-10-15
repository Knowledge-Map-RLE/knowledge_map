"""Пересчитывает прогноз категории результата без карт, цитирующих цель."""
from __future__ import annotations

import json
import logging
import re
from hashlib import sha256
from pathlib import Path

from domain.article_maps import fingerprint, require
from domain.cohort_operation_result_transfer import extract_map as extract_result_map
from domain.cohort_operation_transfer import forecast_for_known_operations, score
from infrastructure.immutable_files import write_immutable
from tools import run_full19_cohort_result_usage_diagnostic as base
from tools.run_full19_cohort_result_usage_permutation import (
    PERMUTATION_COUNT,
    _randomize_links,
)
from tools.run_free_prediction import disable_network


ROOT = Path(r"D:\Knowledge_Map")
OUTPUT = ROOT / (
    "eval/whole_map_forecast/cohort_operation_prediction/"
    "full19-result-usage-citation-holdout-v1"
)
VERSION = "full19-result-usage-citation-heldout-free-type-forecast-1"
CONDITIONAL_MODES = (
    "same_article_cooccurrence",
    "dependency_edges_all_usage",
    "dependency_edges_result_usage",
)
FREE_MODES = (
    "free_same_article_cooccurrence",
    "free_dependency_edges_all_usage",
    "free_dependency_edges_result_usage",
)
MODES = CONDITIONAL_MODES + FREE_MODES
MODE_RU = {
    "same_article_cooccurrence": "Совместная встречаемость без рёбер",
    "dependency_edges_all_usage": "Все прямые связи",
    "dependency_edges_result_usage": "Только связи с меткой `result`",
    "free_same_article_cooccurrence": "Свободный прогноз без рёбер",
    "free_dependency_edges_all_usage": "Свободный прогноз по всем связям",
    "free_dependency_edges_result_usage": "Свободный прогноз по `result`",
}
TARGET_CITATION_PATTERNS = {
    "caracciolo2008": (
        r"Caracciolo\s+(?:B\.?\s*)?2008(?:\s*\[[^\]]+\])?",
        r"Occurrence of cognitive impairment and dementia in the community",
        r"Caracciolo.{0,450}?2008",
    ),
    "katz2012": (
        r"Katz\s+(?:M\.?\s*J\.?\s*)?2012(?:\s*\[[^\]]+\])?",
        r"Age-specific and Sex-specific Prevalence and Incidence of\s+Mild Cognitive Impairment",
    ),
    "roberts2012": (
        r"Roberts\s+(?:R\.?\s*O\.?\s*)?2012(?:\s*\[[^\]]+\])?",
        r"The incidence of MCI differs by subtype",
    ),
}


def _sha(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def _json_bytes(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")


def _normalize_citation_text(text: str) -> str:
    """Сводит переносы и мягкие дефисы, возникающие при извлечении PDF-текста."""
    normalized = text.replace("\u0002", "")
    normalized = re.sub(r"(?<=[A-Za-z])[-‐‑‒–—]\s*(?:\r?\n)\s*(?=[A-Za-z])", "", normalized)
    normalized = re.sub(r"(?<=[A-Za-z])[-‐‑‒–—]\s+(?=[A-Za-z])", "", normalized)
    return re.sub(r"\s+", " ", normalized)


def _citation_matches(
    article_id: str,
    text: str,
    patterns: dict[str, tuple[str, ...]] = TARGET_CITATION_PATTERNS,
) -> list[dict]:
    """Находит библиографические упоминания удерживаемых целей."""
    matches = []
    normalized_text = _normalize_citation_text(text)
    for target_id, target_patterns in patterns.items():
        if target_id == article_id:
            continue
        for pattern in target_patterns:
            match = re.search(pattern, normalized_text, flags=re.IGNORECASE | re.DOTALL)
            if match is None:
                continue
            start = max(0, match.start() - 180)
            end = min(len(normalized_text), match.end() + 260)
            matches.append({
                "target_article_id": target_id,
                "matched_pattern": pattern,
                "offset_encoding": "normalized_citation_text_codepoints",
                "start": match.start(),
                "end": match.end(),
                "snippet": normalized_text[start:end].strip(),
            })
            break
    return matches


def _target_citation_exclusions(source_rows: list[dict], snapshots: dict[str, dict]) -> dict[str, list[dict]]:
    exclusions = {target_id: [] for target_id in TARGET_CITATION_PATTERNS}
    for source in source_rows:
        source_id = source["article_id"]
        matches = _citation_matches(source_id, snapshots[source_id]["source"]["text"])
        for match in matches:
            exclusions[match["target_article_id"]].append({
                "citing_article_id": source_id,
                "citing_map_sha256": source["map_sha256"],
                **match,
            })
    return exclusions


def _predictions(
    rows: dict[str, dict],
    target_id: str,
    excluded_ids: set[str],
    truth_by_article: dict[str, set[tuple[str, str]]],
) -> dict:
    training_ids = sorted(
        source_id for source_id in rows
        if source_id != target_id and source_id not in excluded_ids
    )
    training_all = {
        source_id: rows[source_id]["all_map"] for source_id in training_ids
    }
    training_result = {
        source_id: rows[source_id]["result_map"] for source_id in training_ids
    }
    operations = set(rows[target_id]["all_map"]["operator_families"])
    free_operations = set().union(*(
        set(row["operator_families"]) for row in training_all.values()
    )) if training_all else set()
    all_conditional = forecast_for_known_operations(
        training_all, operations, base.MINIMUM_SUPPORT
    )
    all_free = forecast_for_known_operations(
        training_all, free_operations, base.MINIMUM_SUPPORT
    )
    result_conditional = forecast_for_known_operations(
        training_result, operations, base.MINIMUM_SUPPORT
    )
    result_free = forecast_for_known_operations(
        training_result, free_operations, base.MINIMUM_SUPPORT
    )
    candidate_sets = {
        "same_article_cooccurrence": all_conditional["same_article_cooccurrence"],
        "dependency_edges_all_usage": all_conditional["dependency_edges"],
        "dependency_edges_result_usage": result_conditional["dependency_edges"],
        "free_same_article_cooccurrence": all_free["same_article_cooccurrence"],
        "free_dependency_edges_all_usage": all_free["dependency_edges"],
        "free_dependency_edges_result_usage": result_free["dependency_edges"],
    }
    truth = truth_by_article[target_id]
    scored_modes = {
        mode: score({tuple(pair) for pair in pairs}, truth)
        for mode, pairs in candidate_sets.items()
    }
    return {
        "target_article_id": target_id,
        "scored": bool(truth),
        "truth": [list(pair) for pair in sorted(truth)],
        "known_target_operations": sorted(operations),
        "free_operation_universe": sorted(free_operations),
        "excluded_citing_sources": sorted(excluded_ids),
        "training_source_ids": training_ids,
        "modes": scored_modes,
    }


def _randomized_corpus(rows: dict[str, dict], seed: int) -> dict[str, dict]:
    randomized = {}
    for source_id, row in rows.items():
        all_seed = int(fingerprint([seed, source_id, "all"])[:8], 16)
        result_seed = int(fingerprint([seed, source_id, "result"])[:8], 16)
        all_map, _ = _randomize_links(row["all_map"], all_seed)
        result_map, _ = _randomize_links(row["result_map"], result_seed)
        randomized[source_id] = {
            **row,
            "all_map": all_map,
            "result_map": result_map,
        }
    return randomized


def _aggregate(folds: list[dict]) -> dict:
    aggregate = {
        mode: {"predicted": 0, "target": 0, "hits": 0}
        for mode in MODES
    }
    eligible = [fold for fold in folds if fold["scored"]]
    for fold in eligible:
        for mode in MODES:
            result = fold["modes"][mode]
            aggregate[mode]["predicted"] += result["predicted_count"]
            aggregate[mode]["target"] += result["target_count"]
            aggregate[mode]["hits"] += result["hits"]
    return {"eligible_target_count": len(eligible), "modes": aggregate}


def _permutation_distribution(observed: dict, permutations: list[dict]) -> dict:
    summary = {}
    for mode in MODES:
        observed_hits = observed[mode]["hits"]
        hit_values = [item["modes"][mode]["hits"] for item in permutations]
        prediction_values = [item["modes"][mode]["predicted"] for item in permutations]
        greater_equal = sum(value >= observed_hits for value in hit_values)
        summary[mode] = {
            "observed": observed[mode],
            "permutation_mean_hits": sum(hit_values) / len(hit_values),
            "permutation_min_hits": min(hit_values),
            "permutation_max_hits": max(hit_values),
            "permutation_mean_predictions": sum(prediction_values) / len(prediction_values),
            "permutations_with_hits_at_least_observed": greater_equal,
            "empirical_p_one_sided": (greater_equal + 1) / (len(hit_values) + 1),
        }
    return summary


def _render_ru(result: dict) -> str:
    lines = [
        "# Проверка утечки цитируемой цели в прогнозе категорий результатов",
        "",
        "**Это прогноз категорий результата, не содержания научных выводов.** Сравниваются условный режим (известны операции удержанной статьи) и свободный режим (операции берутся только из обучения).",
        "Для каждой удерживаемой статьи из обучения исключены другие карты, где детерминированный поиск по авторо-годовым и заглавным сигнатурам нашёл прямую ссылку на неё. Сама статья и её целевые связи используются только оценщиком. PMC10000452 по-прежнему исключена по хешу текста.",
        "",
        f"Источников в исходном корпусе: {result['source_count']}; карт с явным целевым `usage=result`: {result['eligible_target_count']}; перестановок: {PERMUTATION_COUNT}; минимум поддержки: {base.MINIMUM_SUPPORT} публикации. Независимость когорт отдельно не подтверждена.",
        "",
        "## Цитатные исключения",
        "",
        "| Цель | Исключённые из её обучения статьи | Основание |",
        "|---|---|---|",
    ]
    for target_id in TARGET_CITATION_PATTERNS:
        rows = result["citation_exclusions"][target_id]
        source_ids = ", ".join(sorted(row["citing_article_id"] for row in rows)) or "нет"
        reasons = "; ".join(sorted({row["matched_pattern"] for row in rows})) or "—"
        lines.append(f"| {target_id} | {source_ids} | {reasons} |")
    lines.extend([
        "",
        "Совпадения проверяются по авторо-годовым формам и заглавиям в сохранённом английском тексте. В JSON сохранены фрагменты и позиции каждого найденного совпадения; координаты даны в нормализованной строке поиска, не в исходном тексте. Фильтр консервативно исключает даже одно только библиографическое цитирование.",
        "",
        "## Результаты на цитатно очищенных фолдах",
        "",
        "| Режим | Совпадения / прогнозы | Целевые пары | Среднее попаданий после перестановки | Перестановок не хуже | Эмпирическое p |",
        "|---|---:|---:|---:|---:|---:|",
    ])
    for mode in MODES:
        observed = result["observed_summary"]["modes"][mode]
        perm = result["permutation_summary"][mode]
        lines.append(
            f"| {MODE_RU[mode]} | {observed['hits']}/{observed['predicted']} | "
            f"{observed['target']} | {perm['permutation_mean_hits']:.3f} | "
            f"{perm['permutations_with_hits_at_least_observed']}/{PERMUTATION_COUNT} | "
            f"{perm['empirical_p_one_sided']:.3f} |"
        )
    lines.extend(["", "## Поцелевые фолды", ""])
    for fold in result["observed_folds"]:
        if not fold["scored"]:
            continue
        excluded = ", ".join(fold["excluded_citing_sources"]) or "нет"
        truth = "; ".join(" → ".join(pair) for pair in fold["truth"])
        lines.extend([
            f"### {fold['target_article_id']}",
            "",
            f"Целевые пары: {truth}. Исключены цитирующие источники: {excluded}.",
            "",
            "| Режим | Совпадения / прогнозы | Совпало | Пропущено | Лишнее |",
            "|---|---:|---|---|---|",
        ])
        for mode in MODES:
            value = fold["modes"][mode]
            show = lambda pairs: "; ".join(" → ".join(pair) for pair in pairs) or "—"
            lines.append(
                f"| {MODE_RU[mode]} | {value['hits']}/{value['predicted_count']} | "
                f"{show(value['matched_pairs'])} | {show(value['missed_pairs'])} | "
                f"{show(value['extra_pairs'])} |"
            )
        lines.append("")
    lines.extend([
        "## Ограничения",
        "",
        "Условные строки используют известные операции удержанной статьи. Свободные строки строят пары только из инвентаря и связей обучающих карт и не читают операции удержанной статьи. Оба режима предсказывают только категории, не научное содержание. Фильтр закрывает найденные прямые цитаты, но эвристический поиск может пропустить необычно оформленную или сильно повреждённую OCR ссылку; транзитивную утечку через другие обзоры он не проверяет. Он также не доказывает независимость остальных источников. Три удержанные публикации дают слишком мало независимых испытаний для общего вывода.",
        "",
        "Независимо от результата этого пересчёта, предыдущий LOPO и его перестановочный `p` нельзя интерпретировать как чистую оценку переноса: аудит обнаружил, что обзор PMC6416157 цитирует и таблично воспроизводит сведения о Caracciolo 2008, Katz 2012 и Roberts 2012; карта Roberts 2012 и карта Luck2010 также содержат ссылку на Caracciolo 2008. Найденные прямые цитаты закрыты от обучения.",
        "",
        "Модельных вызовов — 0; сеть отключена; исходные карты и прежние отчёты не изменены; экспертная научная проверка не проводилась.",
        "",
    ])
    return "\n".join(lines)


def run() -> Path:
    disable_network()
    manifest, source_rows, extracted = base._read_sources()
    snapshots = {
        row["article_id"]: json.loads(Path(row["map_path"]).read_text(encoding="utf-8"))
        for row in source_rows
    }
    all_rows = {
        article_id: {
            "all_map": value,
            "result_map": extract_result_map(snapshots[article_id]),
        }
        for article_id, value in extracted.items()
    }
    truth_by_article = {
        article_id: {tuple(pair) for pair in row["result_map"]["graph_links"]}
        for article_id, row in all_rows.items()
    }
    citation_exclusions = _target_citation_exclusions(source_rows, snapshots)
    eligible_target_ids = sorted(
        article_id for article_id, truth in truth_by_article.items() if truth
    )
    require(set(eligible_target_ids) == set(TARGET_CITATION_PATTERNS),
            "Состав целей с usage=result изменился; требуется пересмотреть настройки аудита")

    observed_folds = [
        _predictions(
            all_rows,
            target_id,
            {row["citing_article_id"] for row in citation_exclusions.get(target_id, [])},
            truth_by_article,
        )
        for target_id in sorted(all_rows)
    ]
    observed_aggregate = _aggregate(observed_folds)
    permutation_aggregates = []
    for seed in range(PERMUTATION_COUNT):
        randomized_rows = _randomized_corpus(all_rows, seed)
        folds = [
            _predictions(
                randomized_rows,
                target_id,
                {row["citing_article_id"] for row in citation_exclusions.get(target_id, [])},
                truth_by_article,
            )
            for target_id in sorted(randomized_rows)
        ]
        permutation_aggregates.append(_aggregate(folds))
    require(all(item["eligible_target_count"] == len(eligible_target_ids)
                for item in permutation_aggregates),
            "Перестановки изменили состав оцениваемых целей")
    observed_modes = observed_aggregate["modes"]
    permutation_summary = _permutation_distribution(
        observed_modes, permutation_aggregates
    )

    implementation_paths = [
        ROOT / "api/tools/run_full19_cohort_result_usage_diagnostic.py",
        ROOT / "api/tools/run_full19_cohort_result_usage_permutation.py",
        ROOT / "api/tools/run_full19_result_usage_citation_holdout.py",
        ROOT / "api/domain/cohort_operation_transfer.py",
        ROOT / "api/domain/cohort_operation_result_transfer.py",
    ]
    implementation = {
        str(path.relative_to(ROOT)): _sha(path.read_bytes())
        for path in implementation_paths
    }
    result = {
        "version": VERSION,
        "source_manifest_sha256": _sha(base.BASE_MANIFEST.read_bytes()),
        "source_count": len(source_rows),
        "sources": source_rows,
        "eligible_target_count": len(eligible_target_ids),
        "minimum_publication_support": base.MINIMUM_SUPPORT,
        "citation_exclusions": citation_exclusions,
        "observed_folds": observed_folds,
        "observed_summary": observed_aggregate,
        "permutation_count": PERMUTATION_COUNT,
        "permutation_policy": "Within each source and mode preserve operation inventory, output inventory, and edge count; exclude direct citers per held-out target before scoring.",
        "permutation_summary": permutation_summary,
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
        "minimum_support": base.MINIMUM_SUPPORT,
        "citation_patterns": TARGET_CITATION_PATTERNS,
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
        "eligible_target_count": len(eligible_target_ids),
        "permutation_count": PERMUTATION_COUNT,
        "citation_holdout_applied": True,
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
    logging.info("full19_result_citation_holdout_complete run=%s perms=%d eligible=%d",
                 run_id, PERMUTATION_COUNT, len(eligible_target_ids))
    return output


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    print(run())


if __name__ == "__main__":
    main()

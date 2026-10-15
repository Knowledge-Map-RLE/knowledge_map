"""Свободный прогноз типов результатов с исключением прямых цитаторов."""
from __future__ import annotations

import argparse
import json
import logging
import re
from hashlib import sha256
from pathlib import Path

from domain.action_result_free_transfer import (
    MINIMUM_SUPPORT, TOP_K, VERSION, score_forecasts, score_permutations,
    seal_forecasts,
)
from domain.article_maps import fingerprint, require
from infrastructure.immutable_files import write_immutable
from tools.run_action_result_transfer import TARGET_SOURCE_SHA256, _load_records
from tools.run_free_prediction import disable_network

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT / (
    "eval/whole_map_forecast/action-result-family-ranking-v2/runs/"
    "b1ddd644e7aec027ed39c69a5068497046e400d25c8229627316129f8914a732/"
    "source-manifest.json"
)
DEFAULT_OUTPUT = ROOT / "eval/whole_map_forecast/action-result-free-citation-audit-v3"
PERMUTATION_SEEDS = tuple(range(100))
CITATION_MATCHER_VERSION = "exact-doi-title-pmcid-author-year-v2"


def normalize_citation_text(text: str) -> str:
    """Нормализует переносы и дефисы PDF без использования внешней модели."""
    normalized = text.replace("\u0002", " ").replace("\u00ad", "")
    normalized = re.sub(r"(?<=[A-Za-z])[-‐‑‒–—]\s*(?=[A-Za-z])", "", normalized)
    normalized = normalized.casefold()
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return " ".join(normalized.split())


def _primary_doi(text: str) -> str | None:
    """Берёт DOI только из шапки статьи, не из списка литературы."""
    header = text[:10000]
    labelled = re.search(
        r"(?im)^\s*(?:\*\*)?doi(?:\*\*)?\s*:?\s*"
        r"(?:https?://(?:dx\.)?doi\.org/)?(10\.\d{4,9}/[^\s<>]+)",
        header,
    )
    if labelled:
        return labelled.group(1).rstrip(".,;)")
    return None


def _primary_pmcid(article_id: str) -> str | None:
    matches = re.findall(r"(?i)PMC\d+", article_id)
    return matches[-1].upper() if matches else None


def citation_metadata(snapshot: dict) -> dict:
    """Возвращает только идентификаторы статьи для фильтрации цитаторов."""
    article_id = snapshot["article_id"]
    title = snapshot.get("article_title") or ""
    source_text = snapshot.get("source", {}).get("text", "")
    author_year_match = re.search(
        r"(?:^|[-_])(?P<author>[a-z]{3,})(?P<year>(?:19|20)\d{2})(?:[-_]|$)",
        article_id,
        flags=re.IGNORECASE,
    )
    return {
        "article_id": article_id,
        "title": title,
        "normalized_title": normalize_citation_text(title),
        "doi": _primary_doi(source_text),
        "normalized_doi": normalize_citation_text(_primary_doi(source_text) or ""),
        "pmcid": _primary_pmcid(article_id),
        "author_year": ({"author": author_year_match.group("author"),
                         "year": author_year_match.group("year")}
                        if author_year_match else None),
    }


def find_direct_citation(source_id: str, source_text: str,
                         target: dict) -> dict | None:
    """Ищет точные DOI, заглавие или PMCID; совпадение трактуется консервативно."""
    if source_id == target["article_id"]:
        return None
    normalized = normalize_citation_text(source_text)
    reasons = []
    if target["normalized_doi"] and target["normalized_doi"] in normalized:
        reasons.append("doi")
    if (target["normalized_title"] and
            len(target["normalized_title"].split()) >= 4 and
            target["normalized_title"] in normalized):
        reasons.append("title")
    if target["pmcid"] and re.search(
            r"(?i)\b" + re.escape(target["pmcid"]) + r"\b", source_text):
        reasons.append("pmcid")
    author_year = target.get("author_year")
    if author_year and re.search(
            r"(?i)\b" + re.escape(author_year["author"]) +
            r"\b[\s\S]{0,500}?\b" + re.escape(author_year["year"]) + r"\b",
            source_text):
        reasons.append("author_year")
    if not reasons:
        return None
    return {
        "target_article_id": target["article_id"],
        "citing_article_id": source_id,
        "matched_identifiers": sorted(set(reasons)),
        "target_title": target["title"],
        "target_doi": target["doi"],
    }


def _json_bytes(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")


def _source_snapshots(manifest: dict) -> dict[str, dict]:
    snapshots = {}
    for row in manifest["sources"]:
        path = Path(row["map_path"])
        snapshot = json.loads(path.read_text(encoding="utf-8"))
        require(snapshot["article_id"] == row["article_id"],
                f"article_id карты не совпадает: {row['article_id']}")
        snapshots[row["article_id"]] = snapshot
    return snapshots


def _citation_exclusions(records: list[dict], snapshots: dict[str, dict]) -> tuple[dict, list]:
    metadata = {article_id: citation_metadata(snapshot)
                for article_id, snapshot in snapshots.items()}
    exclusions = {record["article_id"]: [] for record in records}
    matches = []
    for target_id, target in metadata.items():
        for source_id, snapshot in snapshots.items():
            match = find_direct_citation(
                source_id, snapshot.get("source", {}).get("text", ""), target)
            if match:
                exclusions[target_id].append(match)
                matches.append(match)
    return exclusions, matches


def _report(result: dict) -> str:
    lines = [
        "# Свободный прогноз категорий результата без прямых цитаторов",
        "",
        "**Проверяется тип результата, не содержание научных утверждений.** "
        "Целевые операции, результаты и связи не передаются прогнозчику.",
        "",
        f"Карт: {result['source_count']}; цели исключены по хешу PMC10000452: да; "
        f"минимальная поддержка: {result['minimum_support']} публикации; "
        f"перестановок: {result['permutation_count']}.",
        "",
        "Для каждой цели из обучения удалялись статьи, в полном сохранённом тексте "
        "которых найдены её DOI, точное нормализованное заглавие, PMCID или "
        "сигнатура автора и года из идентификатора публикации. Это "
        "консервативный фильтр: совпадение заглавия в тексте также исключает источник.",
        "",
        "## Результаты свободного прогноза",
        "",
        "| Режим | Кандидатов | Совпадений | Целевых переходов | Точность | Полнота |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    names = {"graph": "Связи графа",
             "without_dependencies": "Те же обучающие статьи без зависимостей"}
    for mode in ("graph", "without_dependencies"):
        metric = result["scores"]["aggregate"][mode]
        precision = "—" if metric["precision"] is None else f"{metric['precision']:.3f}"
        recall = "—" if metric["recall"] is None else f"{metric['recall']:.3f}"
        lines.append(f"| {names[mode]} | {metric['predicted']} | {metric['hits']} | "
                     f"{metric['target']} | {precision} | {recall} |")
    matched_pairs = {}
    for fold in result["scores"]["folds"]:
        for pair in fold["scores"]["graph"]["matched"]:
            key = tuple(pair)
            if key not in matched_pairs:
                matched_pairs[key] = []
            matched_pairs[key].append(fold["target_article_id"])
    lines.extend(["", "Графовые точные совпадения по категориям:", "",
                  "| Предсказанная форма | Совпадений | Отложенные статьи |",
                  "|---|---:|---|"])
    for pair, target_ids in sorted(matched_pairs.items(), key=lambda item: (-len(item[1]), item[0])):
        lines.append(f"| `{pair[0]} → {pair[1]}` | {len(target_ids)} | "
                     f"{', '.join(sorted(target_ids))} |")
    lines.extend(["", "В каждой перестановке сохраняются список операций и число "
                  "связей каждой обучающей статьи, а также общее распределение "
                  "типов результатов по обучающему фолду. Типы результатов "
                  "случайно перераспределяются между этими связями после удаления "
                  "цели и её прямых цитаторов.", "",
                  "| Режим | Наблюдаемые совпадения | Среднее перестановок | Диапазон | "
                  "Перестановок не хуже | Доля с поправкой +1 |",
                  "|---|---:|---:|---:|---:|---:|"])
    for mode in ("graph", "without_dependencies"):
        observed = result["scores"]["aggregate"][mode]["hits"]
        perm = result["permutations"]["summary"][mode]
        lines.append(f"| {names[mode]} | {observed} | {perm['mean_hits']:.2f} | "
                     f"{perm['min_hits']}–{perm['max_hits']} | "
                     f"{perm['runs_at_least_observed']}/{result['permutations']['seed_count']} | "
                     f"{perm['empirical_tail_rate_plus_one']:.3f} |")
    permuted = result["permutations"]
    lines.extend(["",
                  f"Разнообразие контролей: {permuted['unique_prediction_sets']} "
                  f"разных наборов прогнозов и {permuted['unique_ranked_profiles']} "
                  "профилей ранжирования; суммарно по фолдам менялось от "
                  f"{permuted['changed_sources_min']} до {permuted['changed_sources_max']} "
                  "вхождений статьи в обучение и от "
                  f"{permuted['changed_pair_assignments_min']} до "
                  f"{permuted['changed_pair_assignments_max']} назначений связей.",
                  "Доля с поправкой +1 — исследовательская оценка среди заданных "
                  "перестановок, а не подтверждающее статистическое доказательство.", ""])
    lines.extend(["", "## Ранжирование при равном бюджете", "",
                  "При равном числе мест сравниваются кандидаты с наибольшей "
                  "поддержкой среди разных публикаций. Границы одинакового ранга "
                  "оцениваются дробно.", "",
                  "| Кандидатов на цель | Режим | Наблюдаемые ожидаемые совпадения | "
                  "Точность | Полнота | Перестановки: среднее (диапазон) | "
                  "Не хуже наблюдения | Доля с поправкой +1 |",
                  "|---:|---|---:|---:|---:|---:|---:|---:|"])
    for k in TOP_K:
        for mode in ("graph", "without_dependencies"):
            row = result["scores"]["top_k"][str(k)][mode]
            perm = result["permutations"]["summary"][mode]["top_k"][str(k)]
            precision = "—" if row["precision"] is None else f"{row['precision']:.3f}"
            recall = "—" if row["recall"] is None else f"{row['recall']:.3f}"
            lines.append(f"| {k} | {names[mode]} | {row['expected_hits']:.2f} | "
                         f"{precision} | {recall} | {perm['mean_hits']:.2f} "
                         f"({perm['min_hits']:.2f}–{perm['max_hits']:.2f}) | "
                         f"{perm['runs_at_least_observed']}/{result['permutations']['seed_count']} | "
                         f"{perm['empirical_tail_rate_plus_one']:.3f} |")
    lines.extend(["", "## Прямые цитатные исключения", "",
                  f"Всего исключений цель–цитатор: {len(result['citation_matches'])}.", "",
                  "| Цель | Исключённые из её обучения статьи |",
                  "|---|---|"])
    for target_id in sorted(result["citation_exclusions"]):
        ids = sorted({row["citing_article_id"]
                      for row in result["citation_exclusions"][target_id]})
        if ids:
            lines.append(f"| {target_id} | {', '.join(ids)} |")
    lines.extend(["", "## Интерпретация и ограничения", "",
                  "Режим свободный в том смысле, что прогноз перечисляет пары "
                  "операция–результат из обучения и не использует даже семейства "
                  "операций цели. Отрицательный контроль сохраняет список операций "
                  "и число переходов каждой обучающей статьи, а также общее "
                  "распределение результатов; он меняет связь конкретных результатов "
                  "с операциями и не сохраняет распределение результатов по каждой статье.",
                  "",
                  "При равном бюджете граф лучше ранжировал категории на первых "
                  "одном и трёх местах, чем контроль без рёбер; ни одна из 100 "
                  "глобальных перестановок не достигла графовой оценки @1–@3. "
                  "На пяти и десяти местах такого преимущества над перестановками "
                  "нет. При полном наборе пар граф дал 14/97 совпадений, а контроль "
                  "без рёбер — 22/440; все перестановки дали не меньше 14 графовых "
                  "совпадений. Это узкий предварительный сигнал только для ранжирования "
                  "категорий типов результата, не прогноз конкретных научных фактов.",
                  "",
                  "Это ретроспективная проверка уже изученных карт, а не слепой "
                  "предпубликационный прогноз. Фильтр закрывает совпадения DOI, "
                  "заглавия и PMCID, а для идентификаторов с автором и годом — также "
                  "соответствующую авторо-годовую сигнатуру. Он не гарантирует "
                  "обнаружение всех вариантов цитирования, транзитивных ссылок или "
                  "пересекающихся когорт. "
                  "Поддержка считается по публикациям, а не по доказанно независимым "
                  "наборам участников. Совпадение категории не подтверждает "
                  "предсказание направления, величины, значимости или причинности.",
                  "",
                  "Модельных вызовов — 0; сеть отключена; экспертная проверка не "
                  "проводилась. Все материалы и этот отчёт подготовлены на русском языке.",
                  ""])
    return "\n".join(lines)


def run(manifest_path: Path = DEFAULT_MANIFEST,
        output_path: Path = DEFAULT_OUTPUT) -> Path:
    disable_network()
    manifest_raw = manifest_path.read_bytes()
    manifest = json.loads(manifest_raw)
    metadata = manifest.get("metadata", {})
    require(metadata.get("target_article_id_excluded") == "PMC10000452",
            "Манифест должен исключать целевую PMC10000452")
    require(metadata.get("target_source_sha256_excluded") == TARGET_SOURCE_SHA256,
            "Манифест целевой статьи не совпадает с утверждённым хешем")
    records, input_audit = _load_records(manifest)
    snapshots = _source_snapshots(manifest)
    require({row["article_id"] for row in records} == set(snapshots),
            "Состав карт и снимков источника расходится")
    exclusions, citation_matches = _citation_exclusions(records, snapshots)
    sealed = seal_forecasts(records, exclusions, MINIMUM_SUPPORT)
    scores = score_forecasts(records, sealed)
    permutations = score_permutations(records, exclusions, records,
                                      list(PERMUTATION_SEEDS), scores, MINIMUM_SUPPORT)

    implementation_paths = [
        Path(__file__).resolve(),
        Path(__file__).resolve().parents[1] / "domain" / "action_result_free_transfer.py",
        Path(__file__).resolve().parent / "run_action_result_transfer.py",
    ]
    implementation = {str(path.relative_to(ROOT)): sha256(path.read_bytes()).hexdigest()
                      for path in implementation_paths}
    identity = {
        "version": VERSION,
        "manifest_sha256": sha256(manifest_raw).hexdigest(),
        "implementation_sha256": implementation,
        "minimum_support": MINIMUM_SUPPORT,
        "permutation_seeds": list(PERMUTATION_SEEDS),
        "citation_matcher": CITATION_MATCHER_VERSION,
        "target_fields_used": sealed["target_fields_used"],
    }
    run_id = fingerprint(identity)
    result = {
        "run_id": run_id,
        "version": VERSION,
        "source_manifest_sha256": identity["manifest_sha256"],
        "implementation_sha256": implementation,
        "source_count": len(records),
        "minimum_support": MINIMUM_SUPPORT,
        "permutation_count": len(PERMUTATION_SEEDS),
        "citation_matcher_version": CITATION_MATCHER_VERSION,
        "citation_exclusions": exclusions,
        "citation_matches": citation_matches,
        "input_audit": input_audit,
        "sealed_forecasts": sealed,
        "scores": scores,
        "permutations": permutations,
        "target_source_sha256_excluded": TARGET_SOURCE_SHA256,
        "target_operation_families_used": False,
        "target_outcomes_or_dependencies_used": False,
        "network_disabled": True,
        "model_calls": 0,
        "expert_validated": False,
    }
    payloads = {
        "data.json": _json_bytes(result),
        "report.ru.md": _report(result).encode("utf-8"),
        "sealed-prediction.json": _json_bytes(sealed),
    }
    verification = {
        "run_id": run_id,
        "files_sha256": {name: sha256(raw).hexdigest()
                         for name, raw in payloads.items()},
        "source_count": len(records),
        "citation_exclusion_count": len(citation_matches),
        "target_operation_families_used": False,
        "target_outcomes_or_dependencies_used": False,
        "network_disabled": True,
        "model_calls": 0,
        "expert_validated": False,
    }
    payloads["verification.json"] = _json_bytes(verification)
    run_path = output_path / "runs" / run_id
    run_path.mkdir(parents=True, exist_ok=True)
    for name, raw in payloads.items():
        write_immutable(run_path / name, raw)
    logging.info("action_result_free_citation_audit_complete run=%s sources=%d exclusions=%d",
                 run_id, len(records), len(citation_matches))
    return run_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    print(run(args.manifest, args.output))


if __name__ == "__main__":
    main()

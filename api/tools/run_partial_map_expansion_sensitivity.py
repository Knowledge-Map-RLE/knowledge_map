"""Сравнивает LOPO-формы на исходных 21 и расширенных 23 картах."""
from __future__ import annotations

import json
import sys
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API = ROOT / "api"
if str(API) not in sys.path:
    sys.path.insert(0, str(API))

from domain.article_maps import fingerprint, require
from infrastructure.free_prediction_snapshots import FileForecastMaps
from tools import run_training21_operator_transition_lopo as baseline
from tools.import_codex_article_map import prohibit_generation

BASE = ROOT / "eval" / "whole_map_forecast" / "research-corpus-extension-v1" / "pmc10002471-codex-map-v1" / "training21"
BASE_MANIFEST = BASE / "training-corpus-manifest.json"
BASE_SEAL = BASE / "seal-receipt.json"
BASELINE_RESULT = ROOT / "eval" / "whole_map_forecast" / "operator-transition-family-lopo-v1" / "training21" / "data.json"
BASELINE_VERIFICATION = ROOT / "eval" / "whole_map_forecast" / "operator-transition-family-lopo-v1" / "training21" / "verification.json"
OUTPUT = ROOT / "eval" / "whole_map_forecast" / "partial-map-expansion-v1" / "training21-plus-two"
CANDIDATES = (
    "PMC4242065",
    "PMC6376919",
)


def file_sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def candidate_entry(article_id: str) -> dict:
    base = ROOT / "eval" / "whole_map_forecast" / "independent-cohort-maps-v1" / article_id.casefold()
    run_dirs = sorted((base / "runs").iterdir())
    require(len(run_dirs) == 1 and run_dirs[0].is_dir(), f"Ожидался один неизменяемый запуск: {article_id}")
    run = run_dirs[0]
    map_path = run / "map.json"
    coverage_path = run / "coverage.json"
    origin_path = base / "source" / "source-origin.json"
    snapshot = load_json(map_path)
    origin = load_json(origin_path)
    coverage = load_json(coverage_path)
    require(snapshot["article_id"] == origin["pmcid"] == article_id, "Идентификатор источника не совпадает")
    require(snapshot["pipeline_id"] == "text_reified" and snapshot["graph"]["schema_version"] == 6,
            "Ожидалась карта text_reified схемы 6")
    require(snapshot["source"]["sha256"] == origin.get("original_markdown_sha256", origin.get("source_sha256")),
            "Хеш полного текста не совпадает с квитанцией происхождения")
    require(origin["model_calls"] == 0 and origin["expert_validated"] is False,
            "Метаданные происхождения неожиданны")
    require(coverage["complete_source_reviewed"] is True and coverage["references_excluded"] is True,
            "Источник не прошёл заявленную проверку полного текста")
    require(coverage["complete_semantic_coverage"] is False,
            "Этот прогон предназначен только для анализа карт с явно неполным покрытием")
    return {
        "reference": {"article_id": snapshot["article_id"], "pipeline_id": snapshot["pipeline_id"],
                      "run_id": snapshot["run_id"]},
        "path": str(map_path.resolve()),
        "file_sha256": file_sha(map_path),
        "graph_sha256": fingerprint(snapshot["graph"]),
        "source_sha256": snapshot["source"]["sha256"],
        "family": f"publication:{article_id}",
        "published_on": origin["published_on"],
        "published_on_precision": "day",
        "title": origin["title"],
        "support_note": "Полный текст сохранён, но карта неполная; таблицы формализованы не полностью; экспертной проверки и аудита пересечения участников нет.",
        "coverage_artifact": {"path": str(coverage_path.resolve()), "sha256": file_sha(coverage_path)},
        "_origin": origin,
        "_coverage": coverage,
        "_validation": load_json(run / "validation.json"),
    }


def build_rows(entries: list[dict]) -> tuple[list[dict], FileForecastMaps]:
    public_entries = [{key: value for key, value in entry.items() if not key.startswith("_")}
                      for entry in entries]
    repository = FileForecastMaps(public_entries)
    rows = []
    type_catalog = {}
    for entry in public_entries:
        ref = entry["reference"]
        snapshot = repository.get(ref["article_id"], ref["pipeline_id"], repository.owner, ref["run_id"])
        require(snapshot is not None, "Карта из разрешённого манифеста не найдена")
        typed, catalog = baseline.type_shapes(snapshot)
        type_catalog.update(catalog)
        rows.append({"article_id": snapshot["article_id"], "run_id": snapshot["run_id"],
                     "source_sha256": snapshot["source"]["sha256"], "source_text": snapshot["source"]["text"],
                     "citation_keys": baseline.citation_keys(snapshot),
                     "family": entry.get("family", snapshot["article_id"]), **typed})
    return rows, repository


def evaluate(rows: list[dict]) -> dict:
    require(len(rows) == len({row["article_id"] for row in rows}), "В корпусе повторяются article_id")
    article_index = {row["article_id"]: index for index, row in enumerate(rows)}
    graph_support, graph_catalog, cooccur_support, cooccur_catalog = {}, {}, {}, {}
    for mode in baseline.MODES:
        graph_support[mode], graph_catalog[mode] = baseline.graph_supports(rows, mode)
        cooccur_support[mode], cooccur_catalog[mode] = baseline.cooccurrence_supports(rows, mode)

    folds = []
    for target_index, target in enumerate(rows):
        excluded_citations = []
        for source_index, source in enumerate(rows):
            if source_index == target_index:
                continue
            matches = baseline.direct_citation_matches(target["citation_keys"], source["source_text"])
            if matches:
                excluded_citations.append({"article_id": source["article_id"], "evidence": matches})
        excluded_ids = {target["article_id"], *(item["article_id"] for item in excluded_citations)}
        training_ids = {row["article_id"] for row in rows} - excluded_ids
        allowed_mask = sum(1 << article_index[item] for item in training_ids)
        fold_scores, fold_predictions = {}, {}
        truth_by_mode = target["transitions"]
        for mode in baseline.MODES:
            graph_candidates = baseline.candidate_support(graph_support[mode], allowed_mask)
            noedge_candidates = baseline.candidate_support(cooccur_support[mode], allowed_mask)
            fold_scores[mode] = {
                "graph": baseline.ranked(graph_candidates, graph_catalog[mode], truth_by_mode[mode]),
                "cooccurrence": baseline.ranked(noedge_candidates, cooccur_catalog[mode], truth_by_mode[mode]),
            }
            fold_predictions[mode] = {"graph_candidate_count": len(graph_candidates),
                                      "cooccurrence_candidate_count": len(noedge_candidates)}
        folds.append({"target_article_id": target["article_id"], "target_title": target["citation_keys"]["title"],
                      "target_run_id": target["run_id"], "target_source_sha256": target["source_sha256"],
                      "training_article_ids": sorted(training_ids), "training_count": len(training_ids),
                      "excluded_citations": excluded_citations,
                      "target_transition_count": {mode: len(truth_by_mode[mode]) for mode in baseline.MODES},
                      "scores": fold_scores, "candidate_counts": fold_predictions})

    summaries, paired = {}, {}
    for mode in baseline.MODES:
        summaries[mode] = {"graph": {str(k): baseline.aggregate(folds, mode, "graph", str(k)) for k in baseline.TOP_K},
                           "cooccurrence": {str(k): baseline.aggregate(folds, mode, "cooccurrence", str(k)) for k in baseline.TOP_K}}
        paired[mode] = {}
        for budget in map(str, baseline.TOP_K):
            graph_hits = cooccur_hits = wins = losses = ties = 0
            for fold in folds:
                left = fold["scores"][mode]["graph"][budget]["matched_shape_count"]
                right = fold["scores"][mode]["cooccurrence"][budget]["matched_shape_count"]
                graph_hits += left
                cooccur_hits += right
                wins += left > right
                losses += left < right
                ties += left == right
            paired[mode][budget] = {"graph_hits": graph_hits, "cooccurrence_hits": cooccur_hits,
                                    "graph_wins": wins, "cooccurrence_wins": losses, "ties": ties}
    permutation = baseline.permutation_control(rows, folds, article_index)
    return {"folds": folds, "mode_summaries": summaries, "paired_comparison": paired,
            "permutation_control_operator_roles": {key: value for key, value in permutation.items() if key != "scores"},
            "type_catalog_size": {mode: len({row["block_types"][mode][kid]
                                             for row in rows for kid in row["block_types"][mode]})
                                  for mode in baseline.MODES}}


def main() -> None:
    prohibit_generation()
    manifest = load_json(BASE_MANIFEST)
    seal = load_json(BASE_SEAL)
    source_manifest = Path(manifest["metadata"]["source_manifest_path"])
    sealed_predictions = BASE / "sealed" / seal["run_id"] / "predictions.json"
    require(seal["sealed"] and seal["training_count"] == 21, "Исходный корпус не совпадает с запечатанным срезом")
    require(seal["source_manifest_sha256"] == file_sha(source_manifest), "Исходный манифест изменился")
    require(seal["training_manifest_sha256"] == file_sha(BASE_MANIFEST), "Манифест обучения изменился")
    require(seal["prediction_sha256"] == fingerprint(load_json(sealed_predictions)), "Запечатанный прогноз изменился")
    require(seal["target_map_read"] is False and seal["target_map_path_passed"] is False and seal["model_calls"] == 0,
            "Исходный seal нарушает заявленные ограничения")

    base_entries = manifest["sources"]
    base_rows, base_repo = build_rows(base_entries)
    require(len(base_rows) == 21, "Ожидалось 21 исходная публикация")
    previous = load_json(BASELINE_RESULT)
    previous_verification = load_json(BASELINE_VERIFICATION)
    require(file_sha(BASELINE_RESULT) == previous_verification["files"]["data.json"],
            "Хеш сохранённого базового результата не совпадает с квитанцией")
    require(file_sha(Path(baseline.__file__)) == previous_verification["builder_sha256"],
            "Исходный алгоритм изменился после базового аудита")
    require(previous_verification["parent_seal_verified"] is True
            and previous_verification["target_map_read"] is False
            and previous_verification["model_calls"] == 0
            and previous_verification["network_calls"] == 0,
            "Квитанция базового аудита не подтверждает заявленные ограничения")
    require(previous["training_manifest_sha256"] == file_sha(BASE_MANIFEST)
            and previous["source_count"] == 21,
            "Базовый результат относится к другому обучающему корпусу")
    base_result = previous

    additions = [candidate_entry(article_id) for article_id in CANDIDATES]
    add_entries = [{key: value for key, value in entry.items() if not key.startswith("_")} for entry in additions]
    all_entries = [*base_entries, *add_entries]
    base_ids = {entry["reference"]["article_id"] for entry in base_entries}
    require(not (base_ids & set(CANDIDATES)), "Кандидат уже входит в исходный корпус")
    expanded_rows, expanded_repo = build_rows(all_entries)
    require(len(expanded_rows) == 23, "Ожидалось 23 уникальные публикации")
    expanded_result = evaluate(expanded_rows)

    OUTPUT.mkdir(parents=True, exist_ok=True)
    corpus_manifest = {"metadata": {"version": "partial-map-expansion-sensitivity-1",
                                     "parent_training_manifest_sha256": file_sha(BASE_MANIFEST),
                                     "parent_seal_run_id": seal["run_id"],
                                     "source_count": 23, "target_article_id_excluded": seal.get("target_article_id"),
                                     "interpretation": "Ретроспективная LOPO-диагностика структуры; два новых кандидата имеют неполное семантическое покрытие."},
                       "sources": all_entries}
    (OUTPUT / "corpus-manifest.json").write_text(json.dumps(corpus_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = {"audit_version": "partial-map-expansion-sensitivity-1",
              "parent_training_manifest_sha256": file_sha(BASE_MANIFEST),
              "parent_seal_run_id": seal["run_id"],
              "source_count_base": 21, "source_count_expanded": 23,
              "candidate_article_ids": list(CANDIDATES),
              "candidate_coverage": {entry["_origin"]["pmcid"]: {
                  "doi": entry["_origin"]["doi"], "published_on": entry["_origin"]["published_on"],
                  "cohort": entry["_origin"].get("cohort"),
                  "complete_semantic_coverage": entry["_coverage"]["complete_semantic_coverage"],
                  "table_cells_exhaustively_formalized": entry["_coverage"]["table_cells_exhaustively_formalized"],
                  "source_sha256": entry["source_sha256"], "map_sha256": entry["file_sha256"],
                  "knowledge_count": entry["_validation"]["analysis"]["canonical_knowledge_count"],
                  "transition_count": entry["_validation"]["analysis"]["transition_count"],
                  "model_calls": entry["_origin"]["model_calls"], "expert_validated": entry["_origin"]["expert_validated"]}
                  for entry in additions},
              "base_21": {key: value for key, value in base_result.items() if key != "folds"},
              "expanded_23": {key: value for key, value in expanded_result.items() if key != "folds"},
              "base_folds": base_result["folds"], "expanded_folds": expanded_result["folds"],
              "model_calls": 0, "network_calls": 0, "content_prediction": False,
              "incomplete_candidate_maps_allowed_only_for_sensitivity": True}
    (OUTPUT / "data.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report = [
        "# Чувствительность структурного прогноза к двум новым картам",
        "",
        "Это ретроспективная проверка формы переходов при исключении каждой публикации и найденных прямых цитаторов. Она не проверяет совпадение научного содержания.",
        "",
        "## Добавленные карты",
        "",
        "| PMCID | Статья / когорта | Знаний | Переходов | Полное семантическое покрытие | Таблицы исчерпывающе формализованы |",
        "|---|---|---:|---:|---|---|",
    ]
    for entry in additions:
        o, v, c = entry["_origin"], entry["_validation"], entry["_coverage"]
        report.append(f"| {o['pmcid']} | {o['title']} ({o.get('cohort', 'когорта не указана')}) | {v['analysis']['canonical_knowledge_count']} | {v['analysis']['transition_count']} | Нет | Нет |")
    report += ["", "Обе статьи относятся к отдельным когортам по описанию публикации, но перекрытие участников с остальными публикациями полностью не проверено. Эти карты используются только в анализе чувствительности, потому что семантическое покрытие неполное; PMC6376919 сохраняет 72 неформализованные строки таблиц, а таблицы PMC4242065 в сохранённом XML отсутствуют.",
               "", "## Воспроизведение исходной базы", "",
               "Базовые метрики загружены из опубликованного LOPO-аудита. Проверены его SHA-256, хеш обучающего манифеста, исходный seal, точный хеш реализации и все 21 карта через строгий локальный репозиторий. Так мы не тратим время на повторный 1000-кратный перестановочный контроль базы.",
               "", "## Число совпавших форм при равном бюджете @20", "",
               "| Представление | Корпус | По рёбрам графа | Без рёбер | Выигрыши графа / контроль / ничьи по фолдам |",
               "|---|---:|---:|---:|---:|"]
    labels = {"coarse": "Вид знания", "operator_family": "Семейства операторов", "operator_roles": "Семейства + роли/логика"}
    for mode in baseline.MODES:
        for name, value in (("21 исходная карта", base_result), ("23 карты с неполными кандидатами", expanded_result)):
            graph = value["mode_summaries"][mode]["graph"]["20"]["matched_shape_count"]
            noedge = value["mode_summaries"][mode]["cooccurrence"]["20"]["matched_shape_count"]
            paired = value["paired_comparison"][mode]["20"]
            report.append(f"| {labels[mode]} | {name} | {graph} | {noedge} | {paired['graph_wins']} / {paired['cooccurrence_wins']} / {paired['ties']} |")
    p21 = base_result["permutation_control_operator_roles"]
    p23 = expanded_result["permutation_control_operator_roles"]
    report += ["", "## Перестановочный контроль", "",
               f"Для представления «семейства + роли/логика» на исходных картах наблюдалось {p21['observed_graph_matches_at_20']} попаданий; перестановочное среднее {p21['null_mean']:.2f}, p={p21['empirical_one_sided_p']:.4f}.",
               f"После добавления двух неполных карт — {p23['observed_graph_matches_at_20']} попаданий; среднее {p23['null_mean']:.2f}, p={p23['empirical_one_sided_p']:.4f}.",
               "", "## Ограничения интерпретации", "",
               "Даже увеличение числа совпавших форм означало бы перенос типа предпосылок и результата, а не научного утверждения. Отдельный контроль без рёбер показывает, добавляют ли зависимости пользу сверх совместного присутствия тех же видов знаний. Перестановочный контроль проверяет, необычна ли связь конкретных групп предпосылок с типом результата. Неполные карты способны недосчитать реальные переходы; поэтому они не заменяют полные формализации и не могут служить строгой оценкой прогноза.",
               "", "Модельных и сетевых вызовов не было. Использована одна и та же реализация сравнения для обоих срезов; набор из 21 карты совпал с ранее сохранёнными метриками. Целевая карта PMC10002471 не входит в корпус; этот анализ остаётся ретроспективной диагностикой, а не проспективным слепым опытом."]
    report_path = OUTPUT / "report.ru.md"
    report_path.write_text("\n".join(report) + "\n", encoding="utf-8")
    verification = {"audit_version": result["audit_version"], "builder_sha256": file_sha(Path(__file__),),
                    "base_manifest_sha256": file_sha(BASE_MANIFEST), "parent_seal_verified": True,
                    "base_artifact_verified": True,
                    "candidate_map_hashes_verified": {article_id: next(item["file_sha256"] for item in additions if item["_origin"]["pmcid"] == article_id) for article_id in CANDIDATES},
                    "coverage_hashes_verified_by_repository": True,
                    "model_calls": 0, "network_calls": 0,
                    "files": {name: file_sha(OUTPUT / name) for name in ("corpus-manifest.json", "data.json", "report.ru.md")}}
    (OUTPUT / "verification.json").write_text(json.dumps(verification, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT), "base_21": base_result["mode_summaries"],
                      "expanded_23": expanded_result["mode_summaries"],
                      "permutation": {"base_21": p21, "expanded_23": p23}}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

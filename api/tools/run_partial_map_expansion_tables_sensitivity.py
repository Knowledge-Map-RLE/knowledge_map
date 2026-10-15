"""Повторяет LOPO-диагностику с расширенной табличной ревизией PMC6376919."""
from __future__ import annotations

import json
import sys
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API = ROOT / "api"
if str(API) not in sys.path:
    sys.path.insert(0, str(API))

from domain.article_maps import fingerprint, require  # noqa: E402
from tools import run_partial_map_expansion_sensitivity as sensitivity  # noqa: E402
from tools.import_codex_article_map import prohibit_generation  # noqa: E402

BASE = sensitivity.BASE
BASE_MANIFEST = sensitivity.BASE_MANIFEST
BASE_SEAL = sensitivity.BASE_SEAL
BASELINE_RESULT = sensitivity.BASELINE_RESULT
BASELINE_VERIFICATION = sensitivity.BASELINE_VERIFICATION
OUTPUT = ROOT / "eval" / "whole_map_forecast" / "partial-map-expansion-v1" / "training21-plus-tables-v2"
RUN_IDS = {
    "PMC4242065": "2b790be5-6bec-5ffb-9cf4-593b866337c4",
    "PMC6376919": "67617371-6da4-514a-bec0-f8ce0a5c3037",
}
TABLE_ROWS = {
    "Table 1": [*range(33, 42), *range(43, 46)],
    "Table 2": [*range(56, 71), *range(72, 75)],
    "Table 3": [*range(87, 103), *range(104, 107), *range(108, 111)],
    "Table 4": [*range(119, 124), *range(125, 128), *range(129, 132), *range(133, 138)],
}


def file_sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def pinned_candidate_entry(article_id: str) -> dict:
    base = ROOT / "eval" / "whole_map_forecast" / "independent-cohort-maps-v1" / article_id.casefold()
    run = base / "runs" / RUN_IDS[article_id]
    manifest = load_json(run / "manifest.json")
    for relative, expected in manifest["files"].items():
        require(file_sha(run / relative) == expected, f"Хеш артефакта ревизии не совпадает: {article_id}/{relative}")
    map_path = run / "map.json"
    coverage_path = run / "coverage.json"
    origin_path = base / "source" / "source-origin.json"
    snapshot = load_json(map_path)
    origin = load_json(origin_path)
    coverage = load_json(coverage_path)
    novelty = load_json(run / "novelty-status.json")
    validation = load_json(run / "validation.json")
    require(snapshot["article_id"] == origin["pmcid"] == article_id, "Идентификатор источника не совпадает")
    require(snapshot["run_id"] == RUN_IDS[article_id]
            and snapshot["pipeline_id"] == "text_reified"
            and snapshot["graph"]["schema_version"] == 6, "Неожиданный запуск или контракт карты")
    require(snapshot["source"]["sha256"] == origin.get("original_markdown_sha256", origin.get("source_sha256")),
            "Хеш полного текста не совпадает с квитанцией происхождения")
    require(novelty["model_calls"] == 0 and novelty["external_llm_calls"] == 0
            and novelty["local_llm_calls"] == 0 and novelty["embedding_calls"] == 0,
            "Карта не соответствует запрету модельных вызовов")
    require(coverage["complete_source_reviewed"] is True
            and coverage["references_excluded"] is True
            and coverage["complete_semantic_coverage"] is False,
            "Ожидался проверенный полный источник с явно неполной картой")
    if article_id == "PMC6376919":
        statuses = {row["unit_id"]: row["status"] for row in coverage["units"]}
        missing = [f"U{number}" for rows in TABLE_ROWS.values() for number in rows
                   if statuses.get(f"U{number}") != "represented"]
        require(not missing, f"В таблицах остались неформализованные строки данных: {missing}")
        require(coverage.get("main_tables_1_to_4_data_rows_formalized") is True
                and novelty.get("main_tables_1_to_4_data_rows_formalized") is True,
                "Не подтверждено покрытие строк основных таблиц")
        require(validation["contract"] == validation["dag"] == validation["provenance"] == "passed",
                "Расширенная карта не прошла доменную валидацию")
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
        "support_note": ("Основные таблицы 1–4 формализованы построчно; вся статья остаётся выборочно "
                         "формализованной, экспертной проверки нет." if article_id == "PMC6376919"
                         else "Полный источник сохранён; карта имеет неполное семантическое покрытие."),
        "coverage_artifact": {"path": str(coverage_path.resolve()), "sha256": file_sha(coverage_path)},
        "_origin": origin,
        "_coverage": coverage,
        "_validation": validation,
    }


def paired_common_targets(old_result: dict, new_result: dict) -> dict:
    old = {fold["target_article_id"]: fold for fold in old_result["folds"]}
    new = {fold["target_article_id"]: fold for fold in new_result["folds"]}
    common = sorted(set(old) & set(new))
    paired = {}
    for mode in sensitivity.baseline.MODES:
        paired[mode] = {}
        for budget in sensitivity.baseline.TOP_K:
            graph_old = graph_new = noedge_old = noedge_new = wins = losses = ties = 0
            for article_id in common:
                left = old[article_id]["scores"][mode]
                right = new[article_id]["scores"][mode]
                old_graph = left["graph"][str(budget)]["matched_shape_count"]
                new_graph = right["graph"][str(budget)]["matched_shape_count"]
                old_noedge = left["cooccurrence"][str(budget)]["matched_shape_count"]
                new_noedge = right["cooccurrence"][str(budget)]["matched_shape_count"]
                graph_old += old_graph
                graph_new += new_graph
                noedge_old += old_noedge
                noedge_new += new_noedge
                wins += new_graph > old_graph
                losses += new_graph < old_graph
                ties += new_graph == old_graph
            paired[mode][str(budget)] = {
                "common_targets": len(common),
                "graph_old_hits": graph_old,
                "graph_new_hits": graph_new,
                "noedge_old_hits": noedge_old,
                "noedge_new_hits": noedge_new,
                "graph_folds_improved": wins,
                "graph_folds_worsened": losses,
                "graph_folds_tied": ties,
            }
    return paired


def main() -> None:
    prohibit_generation()
    manifest = load_json(BASE_MANIFEST)
    seal = load_json(BASE_SEAL)
    source_manifest = Path(manifest["metadata"]["source_manifest_path"])
    sealed_predictions = BASE / "sealed" / seal["run_id"] / "predictions.json"
    require(seal["sealed"] and seal["training_count"] == 21, "Исходный seal не описывает 21 карту")
    require(seal["source_manifest_sha256"] == file_sha(source_manifest)
            and seal["training_manifest_sha256"] == file_sha(BASE_MANIFEST),
            "Исходный обучающий манифест изменился")
    require(seal["prediction_sha256"] == fingerprint(load_json(sealed_predictions))
            and seal["target_map_read"] is False and seal["target_map_path_passed"] is False
            and seal["model_calls"] == 0, "Нарушен исходный запечатанный прогноз")
    base_entries = manifest["sources"]
    base_ids = {entry["reference"]["article_id"] for entry in base_entries}
    require(len(base_ids) == 21 and "PMC10002471" not in base_ids,
            "Обучающий корпус не совпадает с целевым протоколом")

    previous = load_json(BASELINE_RESULT)
    previous_verification = load_json(BASELINE_VERIFICATION)
    require(file_sha(BASELINE_RESULT) == previous_verification["files"]["data.json"]
            and previous_verification["parent_seal_verified"] is True
            and previous_verification["target_map_read"] is False
            and previous_verification["model_calls"] == previous_verification["network_calls"] == 0
            and previous["training_manifest_sha256"] == file_sha(BASE_MANIFEST)
            and previous["source_count"] == 21,
            "Нельзя воспроизвести исходный результат 21-карточного аудита")

    additions = [pinned_candidate_entry(article_id) for article_id in ("PMC4242065", "PMC6376919")]
    addition_entries = [{key: value for key, value in entry.items() if not key.startswith("_")}
                        for entry in additions]
    all_entries = [*base_entries, *addition_entries]
    require(not (base_ids & {entry["reference"]["article_id"] for entry in addition_entries}),
            "Кандидаты уже входят в исходное обучение")
    old_rows, _ = sensitivity.build_rows(base_entries)
    expanded_rows, _ = sensitivity.build_rows(all_entries)
    require(len(old_rows) == 21 and len(expanded_rows) == 23,
            "Ожидались корпус из 21 и расширенный корпус из 23 статей")
    expanded = sensitivity.evaluate(expanded_rows)
    paired = paired_common_targets(previous, expanded)
    output = {
        "audit_version": "partial-map-expansion-tables-sensitivity-2",
        "parent_training_manifest_sha256": file_sha(BASE_MANIFEST),
        "parent_seal_run_id": seal["run_id"],
        "source_count_base": 21,
        "source_count_expanded": 23,
        "candidate_article_ids": list(RUN_IDS),
        "selected_candidate_run_ids": RUN_IDS,
        "candidate_coverage": {
            entry["_origin"]["pmcid"]: {
                "title": entry["_origin"]["title"],
                "source_sha256": entry["source_sha256"],
                "map_sha256": entry["file_sha256"],
                "run_id": entry["reference"]["run_id"],
                "knowledge_count": entry["_validation"]["analysis"]["canonical_knowledge_count"],
                "statement_count": entry["_validation"]["analysis"]["statement_count"],
                "transition_count": entry["_validation"]["analysis"]["transition_count"],
                "complete_semantic_coverage": entry["_coverage"]["complete_semantic_coverage"],
                "main_tables_1_to_4_data_rows_formalized":
                    entry["_coverage"].get("main_tables_1_to_4_data_rows_formalized", False),
                "model_calls": entry["_origin"]["model_calls"],
                "expert_validated": entry["_origin"]["expert_validated"],
            } for entry in additions
        },
        "base_21": {key: value for key, value in previous.items() if key != "folds"},
        "expanded_23": {key: value for key, value in expanded.items() if key != "folds"},
        "paired_common_targets": paired,
        "base_folds": previous["folds"],
        "expanded_folds": expanded["folds"],
        "model_calls": 0,
        "network_calls": 0,
        "content_prediction": False,
        "interpretation": "Структурная диагностика типов переходов; научное содержание не прогнозировалось.",
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    corpus = {
        "metadata": {
            "version": "partial-map-expansion-tables-sensitivity-2",
            "parent_training_manifest_sha256": file_sha(BASE_MANIFEST),
            "parent_seal_run_id": seal["run_id"],
            "source_count": 23,
            "target_article_id_excluded": "PMC10002471",
            "interpretation": output["interpretation"],
        },
        "sources": all_entries,
    }
    (OUTPUT / "corpus-manifest.json").write_text(json.dumps(corpus, ensure_ascii=False, indent=2) + "\n",
                                                 encoding="utf-8")
    (OUTPUT / "data.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    labels = {"coarse": "Грубый вид знания", "operator_family": "Семейство оператора",
              "operator_roles": "Семейство, роли и логика"}
    report = [
        "# Чувствительность прогноза после формализации таблиц PMC6376919", "",
        "Это ретроспективный leave-one-publication-out тест структурных форм переходов. "
        "Он не прогнозирует факты, численные эффекты или истинность научных выводов.", "",
        "## Новая ревизия карты", "",
        f"PMC6376919: запуск {RUN_IDS['PMC6376919']}, 24 знания, 79 утверждений, 15 переходов; "
        "все 68 строк данных основных таблиц 1–4 связаны с утверждениями, включая строки с отсутствующей оценкой. "
        "Полное семантическое покрытие статьи не заявляется: Supplementary Table S1 отсутствует, экспертной проверки нет.",
        f"PMC4242065: запуск {RUN_IDS['PMC4242065']}, прежняя частичная карта. "
        "Целевой PMC10002471 и найденные прямые цитаторы исключаются из обучения.", "",
        "## Тот же набор из 21 целевой статьи до и после расширения", "",
        "| Представление | Рёбра: до → после | Без рёбер: до → после | Фолды графа: лучше / хуже / равны |",
        "|---|---:|---:|---:|",
    ]
    for mode in sensitivity.baseline.MODES:
        p = paired[mode]["20"]
        report.append(
            f"| {labels[mode]} | {p['graph_old_hits']} → {p['graph_new_hits']} | "
            f"{p['noedge_old_hits']} → {p['noedge_new_hits']} | "
            f"{p['graph_folds_improved']} / {p['graph_folds_worsened']} / {p['graph_folds_tied']} |"
        )
    report += ["", "## Два новых целевых фолда", "",
               "| Целевая карта | Грубая форма: граф / без рёбер | Семейство: граф / без рёбер | Семейство + роли: граф / без рёбер |",
               "|---|---:|---:|---:|"]
    for fold in expanded["folds"]:
        if fold["target_article_id"] not in RUN_IDS:
            continue
        scores = fold["scores"]
        report.append(
            f"| {fold['target_article_id']} | "
            f"{scores['coarse']['graph']['20']['matched_shape_count']} / {scores['coarse']['cooccurrence']['20']['matched_shape_count']} | "
            f"{scores['operator_family']['graph']['20']['matched_shape_count']} / {scores['operator_family']['cooccurrence']['20']['matched_shape_count']} | "
            f"{scores['operator_roles']['graph']['20']['matched_shape_count']} / {scores['operator_roles']['cooccurrence']['20']['matched_shape_count']} |"
        )
    perm = expanded["permutation_control_operator_roles"]
    report += ["", "## Перестановочный контроль", "",
               f"Для семейства, ролей и логики на расширенном корпусе: "
               f"{perm['observed_graph_matches_at_20']} совпадений, нулевая средняя "
               f"{perm['null_mean']:.2f}, эмпирическое p={perm['empirical_one_sided_p']:.4f}.",
               "", "## Границы вывода", "",
               "Сравнение на общих целях показывает, изменилась ли структурная предсказуемость после добавления двух источников; "
               "новая версия PMC6376919 увеличивает табличное покрытие, но остаётся выборочной картой всей статьи. "
               "Грубые совпадения видов знаний не являются совпадениями содержания. "
               "Роль-семантический режим требует более строгих совпадений и может вернуть ноль даже при наличии близких фактов. "
               "Отдельные новые фолды также ретроспективны и не заменяют независимую слепую проверку.",
               "", "Модельных и сетевых вызовов нет. Все результаты и входы сохранены в JSON; исходная карта PMC6376919 и "
               "предыдущий отчёт на 21+2 карты не изменены. Экспертная оценка научной точности не проводилась."]
    (OUTPUT / "report.ru.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    verification = {
        "audit_version": output["audit_version"],
        "runner_sha256": file_sha(Path(__file__)),
        "parent_training_manifest_sha256": file_sha(BASE_MANIFEST),
        "parent_seal_verified": True,
        "base_result_sha256": file_sha(BASELINE_RESULT),
        "selected_run_ids": RUN_IDS,
        "candidate_map_hashes_verified": {entry["_origin"]["pmcid"]: entry["file_sha256"] for entry in additions},
        "all_main_table_data_rows_provenanced": True,
        "model_calls": 0,
        "network_calls": 0,
        "content_prediction": False,
        "files": {name: file_sha(OUTPUT / name) for name in
                  ("corpus-manifest.json", "data.json", "report.ru.md")},
    }
    (OUTPUT / "verification.json").write_text(json.dumps(verification, ensure_ascii=False, indent=2) + "\n",
                                               encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT), "paired_common_targets": paired,
                      "new_target_folds": [
                          {"article_id": fold["target_article_id"], "scores": fold["scores"]}
                          for fold in expanded["folds"] if fold["target_article_id"] in RUN_IDS
                      ],
                      "permutation_control": perm}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

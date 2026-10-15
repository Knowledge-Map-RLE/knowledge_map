"""Проверяет влияние явной маршрутизации табличных утверждений PMC6376919."""
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
from domain.comparison_normalization import normalize_map  # noqa: E402
from tools import run_partial_map_expansion_sensitivity as sensitivity  # noqa: E402
from tools.import_codex_article_map import prohibit_generation  # noqa: E402

BASE = sensitivity.BASE
MANIFEST_PATH = sensitivity.BASE_MANIFEST
SEAL_PATH = sensitivity.BASE_SEAL
PREVIOUS_PATH = ROOT / "eval" / "whole_map_forecast" / "partial-map-expansion-v1" / "training21-plus-tables-v2" / "data.json"
PREVIOUS_VERIFICATION = PREVIOUS_PATH.with_name("verification.json")
OUTPUT_ROOT = ROOT / "eval" / "whole_map_forecast" / "operator-routing-table-audit-v1" / "runs"

# Новые семьи отделяют отсутствие оценки, опорную категорию и редкую ячейку.
TABLE_PREDICATES = {
    "compares baseline category counts": "reported_group_comparison",
    "compares baseline continuous measure": "reported_group_comparison",
    "compares baseline phenotype counts": "reported_group_comparison",
    "reports adjusted domain hazard for later pdd": "reported_model_parameter",
    "reports adjusted subtype hazard": "reported_model_parameter",
    "reports categorical covariate hazard": "reported_model_parameter",
    "reports categorical phenotype hazard": "reported_model_parameter",
    "reports continuous covariate hazard": "reported_model_parameter",
    "reports continuous education hazard": "reported_model_parameter",
    "reports normal cognition reference across models": "reported_model_reference",
    "reports reference phenotype distribution": "reported_sample_summary",
    "reports sparse phenotype category": "reported_sparse_category",
    "reports unavailable subtype estimate": "reported_unavailable_estimate",
    "reports univariate and adjusted association": "reported_model_parameter",
    "associates more than eight years education with lower pd mci hazard": "reported_model_parameter",
    "associates baseline pd mci with later pdd": "reported_association",
}
ROUTING_VERSION = "table-claims-explicit-routing-1"


def file_sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def article_entry(article_id: str, run_id: str) -> dict:
    base = ROOT / "eval" / "whole_map_forecast" / "independent-cohort-maps-v1" / article_id.casefold()
    run = base / "runs" / run_id
    manifest = load_json(run / "manifest.json")
    for relative, expected in manifest["files"].items():
        require(file_sha(run / relative) == expected, f"Хеш карты изменён: {article_id}/{relative}")
    snapshot = load_json(run / "map.json")
    origin = load_json(base / "source" / "source-origin.json")
    novelty = load_json(run / "novelty-status.json")
    require(snapshot["article_id"] == origin["pmcid"] == article_id
            and snapshot["run_id"] == run_id and snapshot["graph_schema_version"] == 6,
            "Идентификатор или контракт выбранной карты изменён")
    require(novelty["model_calls"] == novelty["external_llm_calls"] == novelty["local_llm_calls"] == 0,
            "Входная карта не соответствует ручному происхождению")
    if article_id == "PMC6376919":
        coverage = load_json(run / "coverage.json")
        require(coverage.get("main_tables_1_to_4_data_rows_formalized") is True,
                "Не подтверждено покрытие строк таблиц 1–4")
    return {
        "reference": {"article_id": article_id, "pipeline_id": "text_reified", "run_id": run_id},
        "path": str((run / "map.json").resolve()), "file_sha256": file_sha(run / "map.json"),
        "graph_sha256": fingerprint(snapshot["graph"]), "source_sha256": snapshot["source"]["sha256"],
        "family": f"publication:{article_id}", "published_on": origin["published_on"],
        "published_on_precision": "day", "title": origin["title"],
    }


def main() -> None:
    prohibit_generation()
    manifest = load_json(MANIFEST_PATH)
    seal = load_json(SEAL_PATH)
    previous = load_json(PREVIOUS_PATH)
    previous_verification = load_json(PREVIOUS_VERIFICATION)
    require(seal["sealed"] and seal["training_count"] == 21
            and seal["target_map_read"] is False and seal["model_calls"] == 0,
            "Исходный корпус или seal не проходит проверку")
    require(file_sha(PREVIOUS_PATH) == previous_verification["files"]["data.json"]
            and previous_verification["parent_seal_verified"] is True
            and previous_verification["model_calls"] == previous_verification["network_calls"] == 0
            and previous_verification["content_prediction"] is False,
            "Результат сравнения 21+2 не совпадает с квитанцией")

    entries = list(manifest["sources"])
    base_ids = {entry["reference"]["article_id"] for entry in entries}
    require(len(base_ids) == 21 and "PMC10002471" not in base_ids,
            "Обучающий корпус должен сохранить исходные 21 статьи и исключить цель")
    entries.extend([
        article_entry("PMC4242065", "2b790be5-6bec-5ffb-9cf4-593b866337c4"),
        article_entry("PMC6376919", "67617371-6da4-514a-bec0-f8ce0a5c3037"),
    ])
    require(len({entry["reference"]["article_id"] for entry in entries}) == 23,
            "Новые источники должны быть отдельными от исходного корпуса")

    repository = sensitivity.baseline
    original_routing = repository.PREDICATES
    extended_routing = {**original_routing, **TABLE_PREDICATES}
    collisions = {key for key in TABLE_PREDICATES if key in original_routing
                  and original_routing[key] != TABLE_PREDICATES[key]}
    require(not collisions, f"У новых предикатов обнаружено конфликтующее правило: {sorted(collisions)}")
    repository.PREDICATES = extended_routing
    try:
        rows, _ = sensitivity.build_rows(entries)
        require(len(rows) == 23, "Не удалось восстановить 23 карты по явному allowlist")
        table_snapshot = load_json(Path(next(entry["path"] for entry in entries
                                             if entry["reference"]["article_id"] == "PMC6376919")))
        normalized = normalize_map(table_snapshot)
        routed_table_predicates = {statement["predicate"] for item in normalized
                                   for statement in item["statements"]
                                   if statement["predicate"] in TABLE_PREDICATES}
        require(routed_table_predicates == set(TABLE_PREDICATES),
                "Табличный crosswalk неполон или содержит предикаты, которых нет в карте")
        new_result = sensitivity.evaluate(rows)
    finally:
        repository.PREDICATES = original_routing

    input_binding = {
        "parent_seal_run_id": seal["run_id"],
        "parent_training_manifest_sha256": file_sha(MANIFEST_PATH),
        "previous_23_map_result_sha256": file_sha(PREVIOUS_PATH),
        "candidate_map_hashes": {entry["reference"]["article_id"]: entry["file_sha256"]
                                 for entry in entries if entry["reference"]["article_id"] in {"PMC4242065", "PMC6376919"}},
        "routing_version": ROUTING_VERSION,
        "routing": TABLE_PREDICATES,
    }
    run_id = fingerprint(input_binding)
    output_dir = OUTPUT_ROOT / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    old_folds = {item["target_article_id"]: item for item in previous["expanded_folds"]}
    new_folds = {item["target_article_id"]: item for item in new_result["folds"]}
    require(set(old_folds) == set(new_folds) and len(new_folds) == 23,
            "Парный опыт должен оценивать ровно те же 23 цели")
    paired = {}
    for mode in repository.MODES:
        paired[mode] = {}
        for route, field in (("graph", "graph"), ("no_edges", "cooccurrence")):
            old_total = new_total = 0
            for article_id in sorted(new_folds):
                before = old_folds[article_id]["scores"][mode][field]["20"]["matched_shape_count"]
                after = new_folds[article_id]["scores"][mode][field]["20"]["matched_shape_count"]
                if route == "graph":
                    old_total += before
                    new_total += after
            if route == "graph":
                graph_wins = graph_losses = ties = 0
                for article_id in sorted(new_folds):
                    left = old_folds[article_id]["scores"][mode]["graph"]["20"]["matched_shape_count"]
                    right = new_folds[article_id]["scores"][mode]["graph"]["20"]["matched_shape_count"]
                    graph_wins += right > left
                    graph_losses += right < left
                    ties += right == left
                paired[mode]["same_graph_targets_before_after"] = {
                    "before_hits": old_total, "after_hits": new_total,
                    "folds_improved": graph_wins, "folds_worsened": graph_losses, "folds_tied": ties,
                }
    result = {
        "audit_version": ROUTING_VERSION, "run_id": run_id, "input_binding": input_binding,
        "source_count": 23, "target_article_id_excluded": "PMC10002471",
        "target_count": len(new_result["folds"]), "selected_candidate_runs": {
            "PMC4242065": "2b790be5-6bec-5ffb-9cf4-593b866337c4",
            "PMC6376919": "67617371-6da4-514a-bec0-f8ce0a5c3037"},
        "table_predicates": TABLE_PREDICATES, "routed_table_predicates": sorted(routed_table_predicates),
        "before_after_same_inputs": paired, "mode_summaries": new_result["mode_summaries"],
        "paired_graph_vs_noedge": new_result["paired_comparison"],
        "permutation_control_operator_roles": new_result["permutation_control_operator_roles"],
        "folds": new_result["folds"], "model_calls": 0, "network_calls": 0,
        "scientific_content_prediction": False,
        "interpretation_ru": "Проверка только структурных типов переходов после явной маршрутизации табличных операций; научные факты не прогнозировались.",
    }
    labels = {"coarse": "Грубый вид знания", "operator_family": "Семейства операторов",
              "operator_roles": "Семейства, роли и логика"}
    lines = [
        "# Проверка явной маршрутизации утверждений таблиц PMC6376919", "",
        "Это парная ретроспективная проверка структурных форм. Все 23 источника, тексты, карты, складки, бюджет и порядок ранжирования совпадают с предыдущим запуском; меняется только маршрутизация перечисленных ниже предикатов. Результат не прогнозирует научные факты.", "",
        f"- Версия crosswalk: `{ROUTING_VERSION}`.",
        f"- Источников и целевых складок: 23; целевая статья PMC10002471 исключена из входов.",
        "- Внешних и локальных модельных вызовов: 0; сетевых вызовов: 0.", "",
        "## Сопоставление с прежней маршрутизацией", "",
        "| Представление | Совпадения @20 до → после crosswalk | Лучше / хуже / равно по фолдам |",
        "|---|---:|---:|",
    ]
    for mode in repository.MODES:
        cell = paired[mode]["same_graph_targets_before_after"]
        lines.append(f"| {labels[mode]} | {cell['before_hits']} → {cell['after_hits']} | {cell['folds_improved']} / {cell['folds_worsened']} / {cell['folds_tied']} |")
    lines += ["", "## Рёбра против режима без рёбер после crosswalk", "",
              "| Представление | Графовые попадания @20 | Без рёбер @20 | Фолды: граф лучше / хуже / равно |",
              "|---|---:|---:|---:|"]
    for mode in repository.MODES:
        cell = new_result["paired_comparison"][mode]["20"]
        lines.append(f"| {labels[mode]} | {cell['graph_hits']} | {cell['cooccurrence_hits']} | {cell['graph_wins']} / {cell['cooccurrence_wins']} / {cell['ties']} |")
    lines += ["", "## Явные семьи для новых предикатов", "",
              "Семейство используется только как обобщённый тип операции; исходный предикат, роли, числа, единицы, время, группа и контекст остаются в карте. `reported_model_reference`, `reported_unavailable_estimate` и `reported_sparse_category` намеренно отделены от оценённых эффектов.", "",
              "```json", json.dumps(TABLE_PREDICATES, ensure_ascii=False, indent=2), "```", "",
              "## Ограничения интерпретации", "",
              "Даже структурное попадание не означает совпадение научных выводов или переносимость эффекта. Отбор таблиц не сделал карту PMC6376919 полной; Supplementary Table S1 отсутствует, экспертная валидация не выполнена. Этот прогон — аудит явного словаря типов и не подтверждающий слепой опыт.", ""]
    data_path = output_dir / "data.json"
    report_path = output_dir / "report.ru.md"
    verification_path = output_dir / "verification.json"
    data_content = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    report_content = "\n".join(lines)
    for path, content in ((data_path, data_content), (report_path, report_content)):
        if path.exists():
            require(path.read_text(encoding="utf-8") == content, "Неизменяемый артефакт уже существует с другим содержимым")
        else:
            path.write_text(content, encoding="utf-8")
    verification_content = json.dumps({
        "run_id": run_id, "builder_sha256": file_sha(Path(__file__)),
        "data_sha256": file_sha(data_path), "report_sha256": file_sha(report_path),
        "target_map_read": False, "model_calls": 0, "network_calls": 0,
        "parent_seal_verified": True,
    }, ensure_ascii=False, indent=2) + "\n"
    if verification_path.exists():
        require(verification_path.read_text(encoding="utf-8") == verification_content,
                "Неизменяемая квитанция уже существует с другим содержимым")
    else:
        verification_path.write_text(verification_content, encoding="utf-8")
    print(json.dumps({"run_id": run_id, "report": str(report_path.resolve()),
                      "paired": paired, "graph_vs_noedge": new_result["paired_comparison"],
                      "permutation": result["permutation_control_operator_roles"]},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

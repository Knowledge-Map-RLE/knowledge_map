"""Фиксирует свободный структурно-семантический прогноз до чтения новой цели."""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API = ROOT / "api"
if str(API) not in sys.path:
    sys.path.insert(0, str(API))

from domain.article_maps import fingerprint, require
from infrastructure.free_prediction_snapshots import FileForecastMaps
from tools import run_training21_distinct_unregistered_lopo as previous
from tools import run_training21_operator_transition_lopo as baseline
from tools.operator_route_experiment import MODES, route_table, shape, shape_id, types_for_map

TARGET_ID = "PMC10745259"
TRAINING21 = ROOT / "eval" / "whole_map_forecast" / "research-corpus-extension-v1" / "pmc10002471-codex-map-v1" / "training21"
MANIFEST21 = TRAINING21 / "training-corpus-manifest.json"
SEAL21 = TRAINING21 / "seal-receipt.json"
PREVIOUS_TARGET_META = ROOT / "eval" / "whole_map_forecast" / "research-corpus-extension-v1" / "pmc10002471-codex-map-v1" / "heldout-target.json"
FORECAST_ROOT = ROOT / "eval" / "whole_map_forecast" / "argument-synthesis-holdout-v1" / TARGET_ID.casefold()
TOP_K = (20, 50)
MINIMUM_SUPPORT = 2
ARGUMENT_PATTERN = {
    "arity": 3,
    "source_types": ["state/limitation", "state/result", "state/result"],
    "target_type": "state/conclusion",
}


def file_sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def map_transition_examples(snapshot: dict) -> list[dict]:
    graph = snapshot["graph"]
    knowledge = {item["knowledge_id"]: item for item in graph["knowledge"]}
    nodes = {node["id"]: node["knowledge_id"] for node in graph["nodes"]}
    rows = []
    for transition in graph["transitions"]:
        source_ids = [nodes[item] for item in transition["sources"]]
        target_id = nodes[transition["target"]]
        source_types = [knowledge[key]["kind"] + "/" + knowledge[key]["knowledge_kind"]
                        for key in source_ids]
        target_type = knowledge[target_id]["kind"] + "/" + knowledge[target_id]["knowledge_kind"]
        item_shape = shape(source_types, target_type)
        if shape_id(item_shape) == shape_id(ARGUMENT_PATTERN):
            rows.append({
                "article_id": snapshot["article_id"],
                "sources": [knowledge[key]["display_text"] for key in source_ids],
                "conclusion": knowledge[target_id]["display_text"],
            })
    return rows


def main() -> None:
    require(not FORECAST_ROOT.exists(), "Каталог прогноза уже существует; запечатывание не перезаписывает результаты")
    baseline.prohibit_generation()
    require(previous.verify_pairwise_control(), "Контроль без рёбер не прошёл сверку с полным перебором")
    manifest21 = load_json(MANIFEST21)
    seal21 = load_json(SEAL21)
    previous_target = load_json(PREVIOUS_TARGET_META)
    require(seal21.get("sealed") is True and seal21.get("training_count") == 21
            and seal21.get("target_map_read") is False,
            "Реестр исходных 21 карт не имеет корректной квитанции")
    require(previous_target["reference"]["article_id"] == "PMC10002471",
            "Дополнительный обучающий запуск PMC10002471 изменился")

    extra_entry = {
        "reference": previous_target["reference"],
        "path": previous_target["path"],
        "file_sha256": previous_target["file_sha256"],
        "graph_sha256": None,
        "source_sha256": None,
    }
    previous_target_raw = Path(extra_entry["path"]).read_bytes()
    require(sha256(previous_target_raw).hexdigest() == extra_entry["file_sha256"],
            "Карта PMC10002471 не совпала с ранее запечатанными метаданными")
    previous_target_snapshot = json.loads(previous_target_raw)
    extra_entry["graph_sha256"] = fingerprint(previous_target_snapshot["graph"])
    extra_entry["source_sha256"] = previous_target_snapshot["source"]["sha256"]
    entries = list(manifest21["sources"]) + [extra_entry]
    ids = [item["reference"]["article_id"] for item in entries]
    require(len(ids) == 22 and len(set(ids)) == 22 and TARGET_ID not in ids,
            "Новый целевой PMCID не должен входить в обучающий перечень")

    repository = FileForecastMaps(entries)
    snapshots = []
    rows = []
    source_records = []
    for entry in entries:
        reference = entry["reference"]
        snapshot = repository.get(reference["article_id"], reference["pipeline_id"],
                                  repository.owner, reference["run_id"])
        require(snapshot is not None and snapshot["graph"]["schema_version"] == 6,
                "В обучении отсутствует карта схемы 6")
        require(snapshot["source"]["sha256"] == entry["source_sha256"]
                and fingerprint(snapshot["graph"]) == entry["graph_sha256"]
                and file_sha(Path(entry["path"])) == entry["file_sha256"],
                "Карта или источник не совпали с манифестом")
        typed = types_for_map(snapshot)
        snapshots.append(snapshot)
        rows.append({
            "article_id": snapshot["article_id"],
            "citation_keys": baseline.citation_keys(snapshot),
            "source_text": snapshot["source"]["text"],
            "block_types": typed["block_types"],
            "transitions": typed["transitions"],
        })
        source_records.append({
            "article_id": snapshot["article_id"],
            "run_id": snapshot["run_id"],
            "map_sha256": entry["file_sha256"],
            "graph_sha256": entry["graph_sha256"],
            "source_sha256": entry["source_sha256"],
        })

    target_keys = {"own_pmcid": TARGET_ID.casefold(), "doi": None, "title_key": ""}
    exclusions = []
    for row in rows:
        matches = baseline.direct_citation_matches(target_keys, row["source_text"])
        if matches:
            exclusions.append({"article_id": row["article_id"], "evidence": matches})
    excluded_ids = {item["article_id"] for item in exclusions}
    training_ids = {row["article_id"] for row in rows} - excluded_ids
    article_index = {row["article_id"]: index for index, row in enumerate(rows)}
    allowed_mask = sum(1 << article_index[item] for item in training_ids)

    predictions = {}
    for mode in MODES:
        graph_support, graph_catalog = baseline.graph_supports(rows, mode)
        noedge_support, noedge_catalog = previous.pairwise_cooccurrence_supports(rows, mode)
        predictions[mode] = {}
        for route, support, catalog in (
            ("graph", graph_support, graph_catalog),
            ("without_dependencies", noedge_support, noedge_catalog),
        ):
            candidate_support = baseline.candidate_support(support, allowed_mask)
            ranking = baseline.ranked(candidate_support, catalog, [])
            predictions[mode][route] = {
                budget: ranking[budget]["selected"] for budget in map(str, TOP_K)
            }

    pattern_supporting_articles = []
    for snapshot in snapshots:
        examples = map_transition_examples(snapshot)
        if examples:
            pattern_supporting_articles.append({"article_id": snapshot["article_id"],
                                                "examples": examples})
    require(len(pattern_supporting_articles) >= 2,
            "Кандидатный аргументативный шаблон не поддержан двумя картами")

    target_pattern_id = shape_id(ARGUMENT_PATTERN)
    pattern_ranks = {}
    for mode in MODES:
        pattern_ranks[mode] = {}
        for route in ("graph", "without_dependencies"):
            pattern_ranks[mode][route] = {}
            for budget in map(str, TOP_K):
                selected = predictions[mode][route][budget]
                rank = next((index + 1 for index, item in enumerate(selected)
                             if shape_id(item["shape"]) == target_pattern_id), None)
                pattern_ranks[mode][route][budget] = {
                    "rank_if_in_budget": rank,
                    "predicted": rank is not None,
                    "support_if_predicted": next((item["publication_support"] for item in selected
                                                   if shape_id(item["shape"]) == target_pattern_id), None),
                }

    route_definition = route_table()
    forecast_payload = {
        "version": "free-argument-synthesis-forecast-1",
        "target_article_id": TARGET_ID,
        "target_publication_period": "2024 (bibliographic metadata only)",
        "target_full_text_read": False,
        "target_map_read": False,
        "target_abstract_results_read": False,
        "target_search_snippet_seen_before_seal": True,
        "target_search_snippet_content_ru": "До seal был виден только поисковый фрагмент с целью исследования и общим предметом; результаты и полная аннотация не раскрывались предиктору.",
        "training_source_count": len(rows),
        "training_article_ids": sorted(training_ids),
        "excluded_direct_citations": exclusions,
        "training_manifest_sha256": file_sha(MANIFEST21),
        "prior_target_map_sha256": extra_entry["file_sha256"],
        "route_table_sha256": route_definition["sha256"],
        "minimum_publication_support": MINIMUM_SUPPORT,
        "top_k": list(TOP_K),
        "argument_pattern_candidate": ARGUMENT_PATTERN,
        "argument_pattern_id": target_pattern_id,
        "argument_pattern_support": pattern_supporting_articles,
        "argument_pattern_ranks": pattern_ranks,
        "modes": predictions,
        "source_records": source_records,
        "model_calls": 0,
        "network_calls_during_forecast": 0,
        "scientific_content_prediction": False,
    }
    payload_raw = (json.dumps(forecast_payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    run_id = fingerprint({"forecast_sha256": sha256(payload_raw).hexdigest(),
                          "training_manifest_sha256": file_sha(MANIFEST21),
                          "route_table_sha256": route_definition["sha256"]})
    output = FORECAST_ROOT / "sealed" / run_id
    output.mkdir(parents=True)
    (output / "forecast.json").write_bytes(payload_raw)
    (output / "route-table.json").write_text(json.dumps(route_definition, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    seal = {
        "sealed": True,
        "run_id": run_id,
        "forecast_sha256": sha256(payload_raw).hexdigest(),
        "training_source_count": len(training_ids),
        "training_ids_sha256": fingerprint(sorted(training_ids)),
        "training_manifest_sha256": file_sha(MANIFEST21),
        "prior_target_map_sha256": extra_entry["file_sha256"],
        "route_table_sha256": route_definition["sha256"],
        "target_article_id": TARGET_ID,
        "target_full_text_read": False,
        "target_map_read": False,
        "target_abstract_results_read": False,
        "target_search_snippet_seen_before_seal": True,
        "model_calls": 0,
        "network_calls_during_forecast": 0,
    }
    (output / "seal-receipt.json").write_text(json.dumps(seal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    pattern_text = "ограничение + два эмпирических результата → авторское заключение"
    rank_text = []
    for mode in ("coarse", "exact_operator_family", "curated_operator_family", "curated_operator_roles"):
        for route in ("graph", "without_dependencies"):
            at20 = pattern_ranks[mode][route]["20"]
            at50 = pattern_ranks[mode][route]["50"]
            rank_text.append(f"| {mode} | {route} | {at20['rank_if_in_budget'] or '—'} | {at50['rank_if_in_budget'] or '—'} |")
    report = [
        "# Запечатанный свободный прогноз аргументативной схемы",
        "",
        f"Целевой идентификатор: `{TARGET_ID}`. Полный текст, карта и результаты статьи до seal не читались. До фиксации был виден поисковый фрагмент с общей целью исследования; поэтому это не полностью слепой human review, но сам прогнозирующий сценарий получил только обучающие карты.",
        "",
        f"Обучение: {len(training_ids)} карт schema 6, включая ранее целевую PMC10002471 как прошлый источник; все прямые упоминания PMCID цели проверены и исключены. Предиктор сравнивает видимый граф, тот же набор знаний без зависимостей, точные семьи операторов, уточнённые семьи и роли.",
        "",
        "## Заранее зафиксированная качественная схема",
        "",
        f"**{pattern_text}.** Это прогноз композиции авторского рассуждения, а не содержания результата, направления эффекта, причины или числового значения. Проверяем, появляется ли схема среди первых 20 и 50 кандидатных форм в каждом режиме.",
        "",
        "Поддержка в обучающих источниках:",
        "",
    ]
    for group in pattern_supporting_articles:
        report.append(f"- `{group['article_id']}`: {len(group['examples'])} переход(а/ов) этой формы.")
    report += [
        "",
        "## Ранг замороженного кандидата",
        "",
        "| Уровень типа | Режим | Ранг при @20 | Ранг при @50 |",
        "|---|---|---:|---:|",
        *rank_text,
        "",
        f"Квитанция seal: `{run_id}`. Схема и кандидаты сохранены до открытия целевой карты. Фактическая успешность пока не оценена. Модельных вызовов — 0.",
        "",
    ]
    (output / "forecast.ru.md").write_text("\n".join(report), encoding="utf-8")
    verification = {
        "version": forecast_payload["version"],
        "training_map_count": len(rows),
        "target_absent_from_training": TARGET_ID not in training_ids,
        "all_training_maps_schema6_and_dag": True,
        "target_full_text_read": False,
        "target_map_read": False,
        "target_abstract_results_read": False,
        "model_calls": 0,
        "network_calls_during_forecast": 0,
        "files": {
            "forecast.json": sha256(payload_raw).hexdigest(),
            "forecast.ru.md": file_sha(output / "forecast.ru.md"),
            "route-table.json": file_sha(output / "route-table.json"),
        },
    }
    (output / "verification.json").write_text(json.dumps(verification, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"run_id={run_id}")
    print(f"sources={len(training_ids)}; pattern_support={len(pattern_supporting_articles)}")
    for mode in pattern_ranks:
        print(f"{mode}: graph@20={pattern_ranks[mode]['graph']['20']['rank_if_in_budget']}; graph@50={pattern_ranks[mode]['graph']['50']['rank_if_in_budget']}; no-edge@50={pattern_ranks[mode]['without_dependencies']['50']['rank_if_in_budget']}")
    print(f"sealed={output.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

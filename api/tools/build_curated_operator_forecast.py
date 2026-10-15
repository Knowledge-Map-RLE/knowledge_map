"""Фиксирует структурные прогнозы до доступа к целевой карте."""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
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
from tools.operator_route_experiment import (
    EXPERIMENTAL_FAMILIES, MAXIMUM_ARITY, MODES, route_table, types_for_map,
)

TRAINING = ROOT / "eval" / "whole_map_forecast" / "research-corpus-extension-v1" / "pmc10002471-codex-map-v1" / "training21"
MANIFEST = TRAINING / "training-corpus-manifest.json"
SEAL = TRAINING / "seal-receipt.json"
TARGET_METADATA = ROOT / "eval" / "whole_map_forecast" / "research-corpus-extension-v1" / "pmc10002471-codex-map-v1" / "heldout-target.json"
OUTPUT_ROOT = ROOT / "eval" / "whole_map_forecast" / "curated-operator-route-v1" / "pmc10002471"
TOP_K = (20, 50)
MINIMUM_SUPPORT = 2
MODE = "curated_operator_family"


def file_sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    require(not OUTPUT_ROOT.exists(), "Выход уже существует; запечатанный прогноз нельзя перезаписывать")
    baseline.prohibit_generation()
    require(previous.verify_pairwise_control(), "Контроль без рёбер не прошёл сверку с полным перебором")
    manifest = load_json(MANIFEST)
    parent_seal = load_json(SEAL)
    target_metadata = load_json(TARGET_METADATA)
    require(parent_seal.get("sealed") is True and parent_seal.get("training_count") == 21
            and parent_seal.get("target_map_read") is False and parent_seal.get("target_map_path_passed") is False,
            "Родительский seal обучающей выборки не прошёл проверку")
    require(target_metadata["reference"]["article_id"] == "PMC10002471"
            and target_metadata["reference"]["pipeline_id"] == "text_reified",
            "Метаданные цели изменились")
    route_definition = route_table()
    require(len(route_definition["predicate_to_family"]) == len(set(route_definition["predicate_to_family"])),
            "Маршрутизация должна иметь уникальные ключи")

    repository = FileForecastMaps(manifest["sources"])
    rows = []
    source_records = []
    route_article_support: dict[str, set[str]] = defaultdict(set)
    route_occurrences: Counter = Counter()
    all_predicate_support: dict[str, set[str]] = defaultdict(set)
    for entry in manifest["sources"]:
        reference = entry["reference"]
        snapshot = repository.get(reference["article_id"], reference["pipeline_id"],
                                  repository.owner, reference["run_id"])
        require(snapshot is not None, "Карта обучающего перечня отсутствует")
        require(snapshot["run_id"] == reference["run_id"]
                and snapshot["source"]["sha256"] == entry["source_sha256"]
                and fingerprint(snapshot["graph"]) == entry["graph_sha256"]
                and file_sha(Path(entry["path"])) == entry["file_sha256"],
                "Карта, исходный текст или граф не совпали с манифестом")
        typed = types_for_map(snapshot)
        rows.append({
            "article_id": snapshot["article_id"],
            "citation_keys": baseline.citation_keys(snapshot),
            "source_text": snapshot["source"]["text"],
            "block_types": typed["block_types"],
            "transitions": typed["transitions"],
        })
        for item in snapshot["graph"]["knowledge"]:
            for statement in item["semantic_frame"]["statements"]:
                predicate = statement["predicate"]
                family = route_definition["predicate_to_family"].get(predicate)
                if family in EXPERIMENTAL_FAMILIES:
                    route_article_support[family].add(snapshot["article_id"])
                    route_occurrences[family] += 1
                all_predicate_support[predicate].add(snapshot["article_id"])
        source_records.append({
            "article_id": snapshot["article_id"],
            "run_id": snapshot["run_id"],
            "map_sha256": entry["file_sha256"],
            "graph_sha256": entry["graph_sha256"],
            "source_sha256": entry["source_sha256"],
        })
    require(len(rows) == 21 and "PMC10002471" not in {row["article_id"] for row in rows},
            "Тренировочная выборка должна содержать 21 источник и не содержать целевую карту")
    family_support = {family: len(route_article_support.get(family, set())) for family in EXPERIMENTAL_FAMILIES}
    print("experimental_family_support=" + json.dumps(family_support, sort_keys=True))
    require(all(value >= MINIMUM_SUPPORT for family, value in family_support.items()
                if family != "reported_prevalence")
            and family_support["reported_prevalence"] >= 1,
            "Экспериментальная семья не имеет ожидаемой поддержки в обучении")

    target_id = target_metadata["reference"]["article_id"]
    target_doi = str(target_metadata.get("doi", "")).casefold()
    target_keys = {"own_pmcid": target_id.casefold(), "doi": target_doi,
                   "title_key": ""}
    excluded_citations = []
    for row in rows:
        matches = baseline.direct_citation_matches(target_keys, row["source_text"])
        if matches:
            excluded_citations.append({"article_id": row["article_id"], "evidence": matches})
    excluded_ids = {item["article_id"] for item in excluded_citations}
    training_ids = {row["article_id"] for row in rows} - excluded_ids
    article_index = {row["article_id"]: index for index, row in enumerate(rows)}
    allowed_mask = sum(1 << article_index[article_id] for article_id in training_ids)

    forecasts = {}
    for mode in MODES:
        graph_support, graph_catalog = baseline.graph_supports(rows, mode)
        noedge_support, noedge_catalog = previous.pairwise_cooccurrence_supports(rows, mode)
        forecasts[mode] = {}
        for label, support, catalog in (
            ("graph", graph_support, graph_catalog),
            ("without_dependencies", noedge_support, noedge_catalog),
        ):
            candidates = baseline.candidate_support(support, allowed_mask)
            ranked = baseline.ranked(candidates, catalog, [])
            forecasts[mode][label] = {
                budget: ranked[budget]["selected"]
                for budget in map(str, TOP_K)
            }

    predictions = {
        "version": "curated-operator-route-heldout-forecast-1",
        "target_article_id": target_id,
        "target_doi": target_doi,
        "training_manifest_sha256": file_sha(MANIFEST),
        "parent_seal_run_id": parent_seal["run_id"],
        "source_count": len(rows),
        "excluded_citations": excluded_citations,
        "training_article_ids": sorted(training_ids),
        "modes": forecasts,
        "minimum_publication_support": MINIMUM_SUPPORT,
        "maximum_transition_arity": MAXIMUM_ARITY,
        "top_k": list(TOP_K),
        "route_table_sha256": route_definition["sha256"],
        "route_family_training_support": family_support,
        "route_family_training_occurrences": dict(route_occurrences),
        "source_records": source_records,
        "model_calls": 0,
        "network_calls": 0,
        "target_map_read": False,
        "target_map_path_passed": False,
        "scientific_content_prediction": False,
    }
    prediction_raw = (json.dumps(predictions, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    run_id = fingerprint({"predictions_sha256": sha256(prediction_raw).hexdigest(),
                          "route_table_sha256": route_definition["sha256"]})
    run_dir = OUTPUT_ROOT / "sealed" / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "predictions.json").write_bytes(prediction_raw)
    route_raw = (json.dumps(route_definition, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    (run_dir / "route-table.json").write_bytes(route_raw)
    seal_receipt = {
        "sealed": True,
        "run_id": run_id,
        "prediction_sha256": sha256(prediction_raw).hexdigest(),
        "route_table_sha256": route_definition["sha256"],
        "training_manifest_sha256": file_sha(MANIFEST),
        "target_metadata_sha256": file_sha(TARGET_METADATA),
        "training_count": len(training_ids),
        "all_source_count": len(rows),
        "excluded_citations": excluded_citations,
        "target_map_read": False,
        "target_map_path_passed": False,
        "model_calls": 0,
        "network_calls": 0,
    }
    (run_dir / "seal-receipt.json").write_text(json.dumps(seal_receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = [
        "# Запечатанный прогноз переходов для PMC10002471",
        "",
        "Прогнозы форм переходов получены из 21 карты, запечатаны до чтения карты цели и не содержат новых научных утверждений.",
        "",
        f"- Идентификатор запуска: `{run_id}`.",
        f"- Источников обучения после исключения найденных прямых цитаторов: {len(training_ids)} из {len(rows)}.",
        f"- Поддержка шаблона: минимум {MINIMUM_SUPPORT} публикации; арность: не более {MAXIMUM_ARITY}.",
        f"- Новая версия семейства операторов: `{route_definition['version']}`; хеш: `{route_definition['sha256']}`.",
        "- Сама карта цели и путь к ней в процесс построения не передавались; использованы только PMCID/DOI для исключения явных прямых цитирований.",
        "- LLM, сеть и внешние модели не использовались.",
        "",
        "## Экспериментальные укрупнения типов",
        "",
    ]
    for family, definition in EXPERIMENTAL_FAMILIES.items():
        report.append(f"- **{family}**: поддержка {family_support[family]} источников, {route_occurrences[family]} вхождений. {definition['reason_ru']}")
    report += [
        "",
        "Веса, предикаты, роли и ограничения остаются в исходных снимках; семейство используется только при построении структурного типа. Прогноз оценивает формы DAG, а не эквивалентность фактов, их истинность или причинность.",
        "",
    ]
    (run_dir / "прогноз.ru.md").write_text("\n".join(report), encoding="utf-8")
    print(f"run_id={run_id}")
    print(f"training={len(training_ids)}/{len(rows)}; excluded_citations={len(excluded_citations)}")
    print(f"sealed={run_dir.relative_to(ROOT)}")
    for family in EXPERIMENTAL_FAMILIES:
        print(f"{family}: sources={family_support[family]}, occurrences={route_occurrences[family]}")


if __name__ == "__main__":
    main()

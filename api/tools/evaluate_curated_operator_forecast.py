"""Оценивает запечатанные формы переходов после фиксации прогнозов."""
from __future__ import annotations

import json
import random
import sys
from collections import Counter
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
from tools.operator_route_experiment import MODES, route_table, types_for_map, shape_id

TRAINING = ROOT / "eval" / "whole_map_forecast" / "research-corpus-extension-v1" / "pmc10002471-codex-map-v1" / "training21"
MANIFEST = TRAINING / "training-corpus-manifest.json"
TARGET_METADATA = ROOT / "eval" / "whole_map_forecast" / "research-corpus-extension-v1" / "pmc10002471-codex-map-v1" / "heldout-target.json"
TARGET_MAP = ROOT / "eval" / "whole_map_forecast" / "research-corpus-extension-v1" / "pmc10002471-codex-map-v1" / "runs" / "86f921d6-7bb9-5cd3-a84a-befdc0e83854" / "map.json"
EXPERIMENT = ROOT / "eval" / "whole_map_forecast" / "curated-operator-route-v1" / "pmc10002471"
RUN_ID = "5424c1da25628b4d64117970bac19c99fde27949e26b24c0851d79254ff134d5"
PERMUTATIONS = 1000
SEED = 20261015
MODE = "curated_operator_family"


def file_sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def score(selected: list[dict], truth: list[dict], catalog: dict) -> dict:
    selected_by_id = {shape_id(item["shape"]): item for item in selected}
    truth_by_id = {shape_id(item): item for item in truth}
    matched_ids = sorted(set(selected_by_id).intersection(truth_by_id))
    matches = []
    for key in matched_ids:
        shape = selected_by_id[key]["shape"]
        matches.append({
            "shape": shape,
            "publication_support": selected_by_id[key]["publication_support"],
            "source_descriptors": [catalog.get(type_id) for type_id in shape["source_types"]],
            "target_descriptor": catalog.get(shape["target_type"]),
        })
    target_count = len(truth_by_id)
    selected_count = len(selected_by_id)
    return {
        "predicted_shapes": selected_count,
        "target_shapes": target_count,
        "matched_shapes": len(matched_ids),
        "target_transitions": len(truth),
        "precision": len(matched_ids) / selected_count if selected_count else 0.0,
        "recall": len(matched_ids) / target_count if target_count else 0.0,
        "matches": matches,
    }


def curated_graph_permutation(rows: list[dict], target_truth: list[dict], allowed_ids: set[str]) -> dict:
    article_index = {row["article_id"]: index for index, row in enumerate(rows)}
    allowed_mask = sum(1 << article_index[item] for item in allowed_ids)
    scores = []
    for permutation in range(PERMUTATIONS):
        support: dict[str, int] = {}
        catalog: dict[str, dict] = {}
        for index, row in enumerate(rows):
            if row["article_id"] not in allowed_ids:
                continue
            original = row["transitions"][MODE]
            shuffled_targets = [item["target_type"] for item in original]
            rng = random.Random(SEED + permutation * len(rows) + index * 7919)
            rng.shuffle(shuffled_targets)
            bit = 1 << index
            for item, target_type in zip(original, shuffled_targets):
                changed = {"arity": item["arity"],
                           "source_types": item["source_types"],
                           "target_type": target_type}
                key = baseline.shape_id(changed)
                support[key] = support.get(key, 0) | bit
                catalog[key] = changed
        candidates = baseline.candidate_support(support, allowed_mask)
        selected = sorted(candidates, key=lambda key: (-candidates[key], key))[:20]
        total = baseline.score(selected, target_truth)
        scores.append(total["matched_shape_count"])
    ordered = sorted(scores)
    return {
        "permutation_count": PERMUTATIONS,
        "seed": SEED,
        "scores": scores,
        "null_mean": sum(scores) / len(scores),
        "null_95th_percentile": ordered[round(.95 * (len(ordered) - 1))],
        "null_maximum": ordered[-1],
    }


def main() -> None:
    seal_path = EXPERIMENT / "sealed" / RUN_ID / "seal-receipt.json"
    predictions_path = EXPERIMENT / "sealed" / RUN_ID / "predictions.json"
    route_path = EXPERIMENT / "sealed" / RUN_ID / "route-table.json"
    seal = load_json(seal_path)
    predictions_raw = predictions_path.read_bytes()
    predictions = json.loads(predictions_raw)
    route_definition = load_json(route_path)
    manifest = load_json(MANIFEST)
    require(seal.get("sealed") is True and seal["run_id"] == RUN_ID
            and seal["prediction_sha256"] == sha256(predictions_raw).hexdigest()
            and predictions["training_manifest_sha256"] == file_sha(MANIFEST)
            and predictions["route_table_sha256"] == route_definition["sha256"]
            and route_definition["sha256"] == route_table()["sha256"],
            "Запечатанный прогноз или его версии не совпали")
    require(predictions["target_map_read"] is False and seal["target_map_read"] is False
            and predictions["target_article_id"] == "PMC10002471",
            "Прогноз не прошёл проверку удержания цели")

    # Оценщик открывает целевую карту только после проверки неизменяемой квитанции seal.
    target_metadata = load_json(TARGET_METADATA)
    require(file_sha(TARGET_METADATA) == seal["target_metadata_sha256"]
            and target_metadata["reference"]["article_id"] == predictions["target_article_id"],
            "Идентификатор или метаданные цели изменились после фиксации прогноза")
    target_entry = {
        "reference": target_metadata["reference"],
        "path": str(TARGET_MAP),
        "file_sha256": target_metadata["file_sha256"],
        "graph_sha256": None,
        "source_sha256": None,
    }
    raw_target = TARGET_MAP.read_bytes()
    require(sha256(raw_target).hexdigest() == target_entry["file_sha256"],
            "Целевая карта не совпала с манифестом удержанной цели")
    target_snapshot = json.loads(raw_target)
    target_entry["graph_sha256"] = fingerprint(target_snapshot["graph"])
    target_entry["source_sha256"] = target_snapshot["source"]["sha256"]
    target_repository = FileForecastMaps([target_entry])
    target = target_repository.get("PMC10002471", "text_reified", target_repository.owner,
                                  target_metadata["reference"]["run_id"])
    require(target is not None and target["article_id"] == "PMC10002471",
            "Не удалось безопасно открыть карту цели оценщиком")
    target_types = types_for_map(target)

    evaluation = {}
    for mode in MODES:
        truth = target_types["transitions"][mode]
        catalog = target_types["catalogs"][mode]
        evaluation[mode] = {}
        for route in ("graph", "without_dependencies"):
            evaluation[mode][route] = {}
            for budget in map(str, predictions["top_k"]):
                evaluation[mode][route][budget] = score(
                    predictions["modes"][mode][route][budget], truth, catalog)

    # Повторно загружаются только явно перечисленные обучающие карты для перестановочного контроля.
    repository = FileForecastMaps(manifest["sources"])
    rows = []
    for entry in manifest["sources"]:
        reference = entry["reference"]
        snapshot = repository.get(reference["article_id"], reference["pipeline_id"],
                                  repository.owner, reference["run_id"])
        require(snapshot is not None, "Обучающая карта для контроля отсутствует")
        typed = types_for_map(snapshot)
        rows.append({"article_id": snapshot["article_id"], "transitions": typed["transitions"]})
    allowed_ids = set(predictions["training_article_ids"])
    require(allowed_ids == {row["article_id"] for row in rows},
            "Обучающий набор после исключения цитаторов изменился")
    permutation = curated_graph_permutation(
        rows, target_types["transitions"][MODE], allowed_ids)
    observed = evaluation[MODE]["graph"]["20"]["matched_shapes"]
    permutation["observed_graph_matches_at_20"] = observed
    permutation["empirical_one_sided_p"] = (
        1 + sum(value >= observed for value in permutation["scores"])
    ) / (PERMUTATIONS + 1)
    del permutation["scores"]

    data = {
        "version": "curated-operator-route-heldout-evaluation-1",
        "forecast_run_id": RUN_ID,
        "forecast_sha256": seal["prediction_sha256"],
        "route_table_sha256": route_definition["sha256"],
        "target_article_id": target["article_id"],
        "target_map_sha256": target_entry["file_sha256"],
        "target_graph_sha256": target_entry["graph_sha256"],
        "target_was_opened_after_seal": True,
        "target_was_previously_read_by_codex_for_manual_mapping": True,
        "target_dag_valid": True,
        "evaluation": evaluation,
        "permutation_control_curated_graph_at_20": permutation,
        "scientific_content_prediction": False,
        "graph_advantage_demonstrated": False,
        "model_calls": 0,
        "network_calls": 0,
    }
    data_raw = (json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    output = EXPERIMENT / "evaluation" / RUN_ID
    require(not output.exists(), "Оценка для этого прогноза уже существует и не перезаписывается")
    output.mkdir(parents=True)

    lines = [
        "# Проверка уточнённых операторных типов на PMC10002471",
        "",
        "Это оценка **форм переходов**, а не прогноз конкретных научных фактов. Прогноз был запечатан до открытия карты цели; Codex, однако, ранее читал эту статью при ручной подготовке её карты, поэтому проверка не является слепой для человека.",
        "",
        f"Обучение: 21 карта; прямые цитаторы по DOI/PMCID исключены при построении. Запуск прогноза `{RUN_ID}`. Целевая карта схемы 6 прошла проверку DAG и была открыта только после проверки хеша прогноза.",
        "",
        "## Попадания форм переходов",
        "",
        "| Уровень типа | Режим | @20 совпало / выдано | @20 точность | @50 совпало / выдано | @50 точность |",
        "|---|---|---:|---:|---:|---:|",
    ]
    mode_names = {
        "coarse": "Вид блока",
        "exact_operator_family": "Существующие семьи; неизвестные отдельно",
        "curated_operator_family": "Уточнённые семьи операторов",
        "curated_operator_roles": "Уточнённые семьи и формы ролей",
    }
    for mode in MODES:
        for route, route_name in (("graph", "С зависимостями"), ("without_dependencies", "Без зависимостей")):
            at20, at50 = evaluation[mode][route]["20"], evaluation[mode][route]["50"]
            lines.append(
                f"| {mode_names[mode]} | {route_name} | {at20['matched_shapes']} / {at20['predicted_shapes']} | "
                f"{at20['precision']:.3f} | {at50['matched_shapes']} / {at50['predicted_shapes']} | {at50['precision']:.3f} |"
            )
    lines += [
        "",
        "## Перестановочный контроль",
        "",
        f"Для уточнённых семей с рёбрами: наблюдалось {permutation['observed_graph_matches_at_20']} совпадений при @20; в {PERMUTATIONS} перестановках максимум {permutation['null_maximum']}, среднее {permutation['null_mean']:.2f}, одностороннее `p={permutation['empirical_one_sided_p']:.4f}`. Отсутствие или наличие совпадений формы не подтверждает совпадение смысла.",
        "",
        "## Совпавшие формы уточнённой модели",
        "",
    ]
    matches = evaluation[MODE]["graph"]["20"]["matches"]
    if matches:
        lines += ["| Поддержка в статьях | Арность | Виды исходных знаний | Вид заключения |", "|---:|---:|---|---|"]
        for match in matches:
            shape = match["shape"]
            sources = match["source_descriptors"]
            target_descriptor = match["target_descriptor"]
            source_labels = ", ".join(
                f"{item.get('knowledge_kind', '?')} / {', '.join(item.get('operator_families', []))}"
                if item else "тип не встретился в целевой карте"
                for item in sources
            )
            target_label = (
                f"{target_descriptor.get('knowledge_kind', '?')} / "
                f"{', '.join(target_descriptor.get('operator_families', []))}"
                if target_descriptor else "тип не встретился в целевой карте"
            )
            lines.append(f"| {match['publication_support']} | {shape['arity']} | {source_labels} | {target_label} |")
    else:
        lines.append("Уточнённый графовый режим не выдал ни одной формы, совпавшей с целевой картой при @20.")
    lines += [
        "",
        "## Вывод и ограничения",
        "",
        "Укрупнение предикатов создало экспериментальную иерархию для показателей заболеваемости, распространённости, параметров моделей, статистически не обнаруженных результатов и диагностических критериев. Заболеваемость и распространённость сохранены разными семействами; статистическое необнаружение не трактуется как отсутствие эффекта. Новые семьи — только структурные метки, исходные предикаты, числа, участники и ограничения остаются неизменными.",
        "",
        "Ни один совпавший тип перехода не считается предсказанным фактом. Для утверждения о научном преимуществе нужны совпавшие семантические выводы с ролями, контекстом и источниками, превосходство над теми же знаниями без рёбер, повторение на независимой ранее не читанной целевой статье и экспертная проверка. Эта диагностика сама по себе цель свободного научного прогнозирования не достигает.",
        "",
        "Модельных и сетевых вызовов — 0. Production-словарь, GOLD и карты UI не менялись.",
        "",
    ]
    report_raw = "\n".join(lines).encode("utf-8")
    (output / "data.json").write_bytes(data_raw)
    (output / "report.ru.md").write_bytes(report_raw)
    verification = {
        "version": data["version"],
        "forecast_seal_valid": True,
        "target_opened_after_seal": True,
        "target_schema6_dag_and_provenance_valid": True,
        "target_map_previously_read_by_codex": True,
        "model_calls": 0,
        "network_calls": 0,
        "files": {"data.json": sha256(data_raw).hexdigest(),
                  "report.ru.md": sha256(report_raw).hexdigest()},
    }
    (output / "verification.json").write_text(json.dumps(verification, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"evaluation={output.relative_to(ROOT)}")
    for mode in MODES:
        graph = evaluation[mode]["graph"]["20"]
        noedge = evaluation[mode]["without_dependencies"]["20"]
        print(f"{mode}: graph={graph['matched_shapes']}/{graph['predicted_shapes']}; no-edge={noedge['matched_shapes']}/{noedge['predicted_shapes']}")
    print(f"curated_graph_permutation_p={permutation['empirical_one_sided_p']:.4f}")


if __name__ == "__main__":
    main()

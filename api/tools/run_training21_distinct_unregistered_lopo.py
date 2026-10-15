"""Повторяет удержанный прогноз, сохраняя неизвестные предикаты раздельными."""
from __future__ import annotations

import itertools
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
from domain.development_prediction import validate_visible_dag
from domain.operator_frame_routing import PREDICATES, VERSION as ROUTING_VERSION, DICTIONARY_SHA256
from infrastructure.free_prediction_snapshots import FileForecastMaps
from tools import run_training21_operator_transition_lopo as baseline

TRAINING = ROOT / "eval" / "whole_map_forecast" / "research-corpus-extension-v1" / "pmc10002471-codex-map-v1" / "training21"
MANIFEST_PATH = TRAINING / "training-corpus-manifest.json"
SEAL_PATH = TRAINING / "seal-receipt.json"
OUTPUT = ROOT / "eval" / "whole_map_forecast" / "operator-transition-distinct-unregistered-v1" / "training21"
MODE = "operator_family_distinct_unregistered"
TOP_K = (20, 50)
MINIMUM_SUPPORT = 2
MAXIMUM_ARITY = 3
PERMUTATIONS = 1000
SEED = 20261015
IMPLEMENTATION = (
    Path(__file__),
    Path(__file__).with_name("run_training21_operator_transition_lopo.py"),
    ROOT / "api" / "domain" / "operator_frame_routing.py",
)


def file_sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def distinct_type_shapes(snapshot: dict) -> tuple[dict, dict, Counter]:
    graph = snapshot["graph"]
    validate_visible_dag(graph)
    normalized = {item["id"]: item for item in baseline.normalize_map(snapshot)}
    knowledge = {item["knowledge_id"]: item for item in graph["knowledge"]}
    block_types = {}
    catalog = {}
    predicate_counts = Counter()
    for knowledge_id, item in knowledge.items():
        frame = normalized[knowledge_id]
        operators = []
        for statement in frame["statements"]:
            predicate = statement["predicate"]
            if predicate in PREDICATES:
                operators.append(PREDICATES[predicate])
            else:
                operators.append("unregistered:" + predicate)
                predicate_counts[predicate] += 1
        payload = {
            "kind": item["kind"],
            "knowledge_kind": item["knowledge_kind"],
            "action_status": item["action_status"],
            "logic": frame["logic"],
            "operator_families": sorted(set(operators)),
        }
        type_id = "operator_family:" + fingerprint(payload)
        block_types[knowledge_id] = type_id
        catalog[type_id] = payload

    node_to_knowledge = {node["id"]: node["knowledge_id"] for node in graph["nodes"]}
    transitions = []
    for transition in graph["transitions"]:
        source_ids = [node_to_knowledge[node_id] for node_id in transition["sources"]]
        target_id = node_to_knowledge[transition["target"]]
        if len(source_ids) > MAXIMUM_ARITY:
            continue
        transitions.append(baseline.shape(
            [block_types[key] for key in source_ids],
            block_types[target_id],
        ))
    return {"block_types": {MODE: block_types}, "transitions": {MODE: transitions}}, catalog, predicate_counts


def pairwise_cooccurrence_supports(rows: list[dict], mode: str) -> tuple[dict[str, int], dict[str, dict]]:
    """Считает только формы с поддержкой минимум в двух статьях."""
    counts_by_article = [
        Counter(row["block_types"][mode].values())
        for row in rows
    ]
    support: dict[str, int] = {}
    catalog: dict[str, dict] = {}
    for left in range(len(rows)):
        counts_left = counts_by_article[left]
        bit_left = 1 << left
        for right in range(left + 1, len(rows)):
            counts_right = counts_by_article[right]
            common_types = sorted(set(counts_left).intersection(counts_right))
            if not common_types:
                continue
            pair_bits = bit_left | (1 << right)
            for arity in range(1, MAXIMUM_ARITY + 1):
                for source_types in itertools.combinations_with_replacement(common_types, arity):
                    required = Counter(source_types)
                    for target_type in common_types:
                        required[target_type] += 1
                        if all(counts_left[key] >= count and counts_right[key] >= count
                               for key, count in required.items()):
                            candidate = baseline.shape(list(source_types), target_type)
                            key = baseline.shape_id(candidate)
                            support[key] = support.get(key, 0) | pair_bits
                            catalog[key] = candidate
                        required[target_type] -= 1
                        if required[target_type] == 0:
                            del required[target_type]
    return support, catalog


def verify_pairwise_control() -> bool:
    rows = [
        {"block_types": {"probe": {"a1": "A", "a2": "A", "b1": "B"}}},
        {"block_types": {"probe": {"a1": "A", "b1": "B", "b2": "B"}}},
        {"block_types": {"probe": {"a1": "A", "c1": "C"}}},
        {"block_types": {"probe": {"a1": "A", "a2": "A", "c1": "C"}}},
    ]
    naive_support_all, naive_catalog_all = baseline.cooccurrence_supports(rows, "probe")
    naive_support = {key: mask for key, mask in naive_support_all.items()
                     if mask.bit_count() >= MINIMUM_SUPPORT}
    naive_catalog = {key: naive_catalog_all[key] for key in naive_support}
    pair_support, pair_catalog = pairwise_cooccurrence_supports(rows, "probe")
    require(naive_support == pair_support and naive_catalog == pair_catalog,
            "Оптимизированный no-edge-контроль расходится с полным перебором на малом корпусе")
    return True


def permutation_control(rows: list[dict], folds: list[dict], article_index: dict[str, int]) -> dict:
    observed = sum(fold["scores"][MODE]["graph"]["20"]["matched_shape_count"] for fold in folds)
    scores = []
    for permutation in range(PERMUTATIONS):
        total_hits = 0
        for fold_number, fold in enumerate(folds):
            target_index = article_index[fold["target_article_id"]]
            allowed_ids = set(fold["training_article_ids"])
            support: dict[str, int] = {}
            catalog: dict[str, dict] = {}
            for article_id in sorted(allowed_ids):
                index = article_index[article_id]
                original = rows[index]["transitions"][MODE]
                targets = [item["target_type"] for item in original]
                rng = random.Random(SEED + permutation * len(folds) + fold_number * 7919 + index)
                rng.shuffle(targets)
                bit = 1 << index
                for item, target_type in zip(original, targets):
                    changed = baseline.shape(item["source_types"], target_type)
                    key = baseline.shape_id(changed)
                    baseline.add_bit(support, key, bit)
                    catalog[key] = changed
            allowed_mask = sum(1 << article_index[item] for item in allowed_ids)
            candidates = baseline.candidate_support(support, allowed_mask)
            selected = sorted(candidates, key=lambda key: (-candidates[key], key))[:20]
            truth = rows[target_index]["transitions"][MODE]
            total_hits += baseline.score(selected, truth)["matched_shape_count"]
        scores.append(total_hits)
    ordered = sorted(scores)
    return {
        "permutation_count": PERMUTATIONS,
        "seed": SEED,
        "observed_graph_matches_at_20": observed,
        "null_mean": sum(scores) / len(scores),
        "null_95th_percentile": ordered[round(.95 * (len(ordered) - 1))],
        "null_maximum": ordered[-1],
        "empirical_one_sided_p": (1 + sum(value >= observed for value in scores)) / (len(scores) + 1),
        "scores": scores,
    }


def write_new(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)


def main() -> None:
    require(not OUTPUT.exists(), "Выходная папка уже существует; неизменяемый аудит не перезаписывается")
    baseline.prohibit_generation()
    require(verify_pairwise_control(), "Проверка no-edge-контроля не завершилась")
    manifest = load_json(MANIFEST_PATH)
    seal = load_json(SEAL_PATH)
    source_manifest = Path(manifest["metadata"]["source_manifest_path"])
    sealed_predictions = TRAINING / "sealed" / seal["run_id"] / "predictions.json"
    require(seal["sealed"] and seal["training_count"] == 21
            and seal["source_manifest_sha256"] == file_sha(source_manifest)
            and seal["training_manifest_sha256"] == file_sha(MANIFEST_PATH)
            and seal["prediction_sha256"] == fingerprint(load_json(sealed_predictions))
            and seal["target_map_read"] is False and seal["target_map_path_passed"] is False
            and seal["model_calls"] == 0,
            "Родительский seal не прошёл проверку")

    repository = FileForecastMaps(manifest["sources"])
    rows = []
    source_records = []
    unregistered_counts = Counter()
    for entry in manifest["sources"]:
        reference = entry["reference"]
        snapshot = repository.get(reference["article_id"], reference["pipeline_id"],
                                  repository.owner, reference["run_id"])
        require(snapshot is not None, "Карта обучающего списка не найдена")
        require(snapshot["run_id"] == reference["run_id"]
                and snapshot["source"]["sha256"] == entry["source_sha256"]
                and fingerprint(snapshot["graph"]) == entry["graph_sha256"]
                and file_sha(Path(entry["path"])) == entry["file_sha256"],
                "Карта, источник или граф не совпадают с манифестом")
        typed, catalog, unknown = distinct_type_shapes(snapshot)
        unregistered_counts.update(unknown)
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
    require(len(rows) == 21 and len({row["article_id"] for row in rows}) == 21,
            "Ожидались 21 уникальная карта")

    graph_support, graph_catalog = baseline.graph_supports(rows, MODE)
    noedge_support, noedge_catalog = pairwise_cooccurrence_supports(rows, MODE)
    article_index = {row["article_id"]: index for index, row in enumerate(rows)}
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
        graph_candidates = baseline.candidate_support(graph_support, allowed_mask)
        noedge_candidates = baseline.candidate_support(noedge_support, allowed_mask)
        truth = target["transitions"][MODE]
        folds.append({
            "target_article_id": target["article_id"],
            "target_title": target["citation_keys"]["title"],
            "training_article_ids": sorted(training_ids),
            "training_count": len(training_ids),
            "excluded_citations": excluded_citations,
            "target_shape_count": len({baseline.shape_id(item) for item in truth}),
            "target_transition_count": len(truth),
            "scores": {
                MODE: {
                    "graph": baseline.ranked(graph_candidates, graph_catalog, truth),
                    "cooccurrence": baseline.ranked(noedge_candidates, noedge_catalog, truth),
                }
            },
        })

    summaries = {
        route: {str(k): baseline.aggregate(folds, MODE, route, str(k)) for k in TOP_K}
        for route in ("graph", "cooccurrence")
    }
    paired = {}
    for budget in map(str, TOP_K):
        graph_hits = [fold["scores"][MODE]["graph"][budget]["matched_shape_count"] for fold in folds]
        noedge_hits = [fold["scores"][MODE]["cooccurrence"][budget]["matched_shape_count"] for fold in folds]
        paired[budget] = {
            "graph_hits": sum(graph_hits),
            "cooccurrence_hits": sum(noedge_hits),
            "graph_wins": sum(a > b for a, b in zip(graph_hits, noedge_hits)),
            "cooccurrence_wins": sum(a < b for a, b in zip(graph_hits, noedge_hits)),
            "ties": sum(a == b for a, b in zip(graph_hits, noedge_hits)),
        }
    permutation = permutation_control(rows, folds, article_index)

    result = {
        "audit_version": "operator-transition-distinct-unregistered-training21-1",
        "training_manifest_sha256": file_sha(MANIFEST_PATH),
        "source_manifest_sha256": file_sha(source_manifest),
        "parent_seal_run_id": seal["run_id"],
        "parent_prediction_sha256": seal["prediction_sha256"],
        "source_count": len(rows),
        "minimum_publication_support": MINIMUM_SUPPORT,
        "maximum_transition_arity": MAXIMUM_ARITY,
        "top_k": list(TOP_K),
        "operator_routing_version": ROUTING_VERSION,
        "operator_routing_dictionary_sha256": DICTIONARY_SHA256,
        "unregistered_predicate_policy": "Каждый неизвестный нормализованный предикат остаётся отдельным значением unregistered:<predicate>.",
        "unregistered_predicate_occurrences": sum(unregistered_counts.values()),
        "unregistered_predicate_counts": dict(sorted(unregistered_counts.items())),
        "noedge_algorithm": "Попарное пересечение наборов типов блоков; в множество кандидатов попадают только формы, встречающиеся хотя бы в двух источниках.",
        "noedge_control_fixture_verified": True,
        "summaries": summaries,
        "paired_comparison": paired,
        "permutation_control": {key: value for key, value in permutation.items() if key != "scores"},
        "folds": folds,
        "source_records": source_records,
        "model_calls": 0,
        "network_calls": 0,
        "target_map_read": False,
        "scientific_content_prediction": False,
    }

    report = [
        "# Удержанный прогноз с отдельными неизвестными предикатами",
        "",
        "В предыдущем варианте все не зарегистрированные предикаты объединялись в один тип. Разбор совпадений показал, что это сводило разные методы и результаты к общей форме. В этой версии неизвестные предикаты остаются отдельными.",
        "",
        f"- Источников: {len(rows)}; поддержка: минимум {MINIMUM_SUPPORT} публикации; не более {MAXIMUM_ARITY} предпосылок.",
        f"- Прямые цитаторы цели исключены из каждого обучающего фолда.",
        f"- Нераспознанных предикатных вхождений сохранено отдельно: {sum(unregistered_counts.values())}; уникальных форм: {len(unregistered_counts)}.",
        "- Оптимизированный контроль без рёбер точно совпал с полным перебором на малом проверочном корпусе.",
        "- Модельных и сетевых вызовов: 0; карта PMC10002471 не передавалась обучающей части.",
        "",
        "## Результаты при одинаковом бюджете",
        "",
        "| Лимит | Граф: совпало / выдано | Без рёбер: совпало / выдано | Выигрыш графа / контроля / ничья |",
        "|---:|---:|---:|---:|",
    ]
    for budget in map(str, TOP_K):
        graph = summaries["graph"][budget]
        noedge = summaries["cooccurrence"][budget]
        comparison = paired[budget]
        report.append(
            f"| @{budget} | {graph['matched_shape_count']} / {graph['predicted_shape_count']} | "
            f"{noedge['matched_shape_count']} / {noedge['predicted_shape_count']} | "
            f"{comparison['graph_wins']} / {comparison['cooccurrence_wins']} / {comparison['ties']} |"
        )
    report += [
        "",
        "## Перестановочный контроль",
        "",
        f"При @20 наблюдалось {permutation['observed_graph_matches_at_20']} совпадений. "
        f"В {PERMUTATIONS} перестановках среднее равно {permutation['null_mean']:.2f}, "
        f"95-й процентиль — {permutation['null_95th_percentile']}, максимум — {permutation['null_maximum']}; "
        f"эмпирическое одностороннее p = {permutation['empirical_one_sided_p']:.4f}.",
        "",
        "## Интерпретация",
        "",
        "Сопоставление с предыдущей версией показывает, исчезает ли структурный сигнал после разделения неизвестных предикатов. Совпадение формы перехода всё ещё не означает совпадения утверждений, участников или условий.",
        "",
        "Это ретроспективная LOPO-диагностика на уже известных картах. Она прогнозирует только формы переходов, а не научное содержание. Пересечение участников когорт и экспертная корректность исходных карт не установлены.",
        "",
        "## Воспроизводимость",
        "",
        f"Seal обучающего корпуса: {seal['run_id']}. Манифест: {file_sha(MANIFEST_PATH)}.",
        f"Версия словаря операторов: {ROUTING_VERSION}; хеш: {DICTIONARY_SHA256}.",
        "Полные предсказания, фолды, цитатные исключения и происхождение карт сохранены в data.json.",
    ]
    report_raw = ("\n".join(report) + "\n").encode("utf-8")
    data_raw = (json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    write_new(OUTPUT / "training-corpus-manifest.json", MANIFEST_PATH.read_bytes())
    for path in IMPLEMENTATION:
        write_new(OUTPUT / "implementation" / path.relative_to(ROOT), path.read_bytes())
    write_new(OUTPUT / "data.json", data_raw)
    write_new(OUTPUT / "report.ru.md", report_raw)
    receipt = {
        "audit_version": result["audit_version"],
        "builder_sha256": file_sha(Path(__file__)),
        "implementation_sha256": {str(path.relative_to(ROOT)): file_sha(path) for path in IMPLEMENTATION},
        "artifacts_sha256": {
            "training-corpus-manifest.json": file_sha(OUTPUT / "training-corpus-manifest.json"),
            "data.json": file_sha(OUTPUT / "data.json"),
            "report.ru.md": file_sha(OUTPUT / "report.ru.md"),
        },
        "parent_seal_verified": True,
        "target_map_read": False,
        "model_calls": 0,
        "network_calls": 0,
    }
    write_new(OUTPUT / "verification.json",
              (json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8"))
    require(file_sha(OUTPUT / "report.ru.md") == receipt["artifacts_sha256"]["report.ru.md"],
            "Хеш отчёта не совпал")
    print(json.dumps({"summaries": summaries, "paired": paired,
                      "permutation": {key: value for key, value in permutation.items() if key != "scores"},
                      "output": str(OUTPUT)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

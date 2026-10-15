"""Сравнивает перенос форм переходов с типами операторов на удержанных картах."""
from __future__ import annotations

import itertools
import json
import math
import random
import re
import sys
from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path
from statistics import mean, pstdev

ROOT = Path(__file__).resolve().parents[2]
API = ROOT / "api"
if str(API) not in sys.path:
    sys.path.insert(0, str(API))

from domain.article_maps import fingerprint, require
from domain.comparison_normalization import normalize, normalize_map
from domain.development_prediction import validate_visible_dag
from domain.operator_frame_routing import (DICTIONARY_SHA256 as ROUTING_SHA256,
                                           PREDICATES, VERSION as ROUTING_VERSION)
from infrastructure.free_prediction_snapshots import FileForecastMaps
from tools.import_codex_article_map import prohibit_generation


BASE = ROOT / "eval" / "whole_map_forecast" / "research-corpus-extension-v1" / "pmc10002471-codex-map-v1"
TRAINING = BASE / "training21"
MANIFEST_PATH = TRAINING / "training-corpus-manifest.json"
SEAL_PATH = TRAINING / "seal-receipt.json"
OUTPUT = ROOT / "eval" / "whole_map_forecast" / "operator-transition-family-lopo-v1" / "training21"
MINIMUM_SUPPORT = 2
MAXIMUM_ARITY = 3
TOP_K = (20, 50)
PERMUTATION_COUNT = 1000
PERMUTATION_SEED = 20261015
DOI_RE = re.compile(r"\b(10\.\d{4,9}/[A-Z0-9._;()/:+-]+)", re.IGNORECASE)
PMCID_RE = re.compile(r"\bPMC\d+\b", re.IGNORECASE)
TOKEN_RE = re.compile(r"[a-z0-9]+")
MODES = ("coarse", "operator_family", "operator_roles")


def file_sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def normalized_text(text: str) -> str:
    return " ".join(TOKEN_RE.findall(text.casefold().replace("\u00ad", "")))


def citation_keys(article: dict) -> dict:
    text = article["source"]["text"]
    doi = DOI_RE.search(text)
    headings = re.findall(r"(?m)^#\s+(.+?)\s*$", text)
    title = headings[0].strip() if headings else ""
    title_key = " ".join(TOKEN_RE.findall(title.casefold()))
    pmcids = PMCID_RE.findall(article["article_id"])
    return {"doi": doi.group(1).rstrip(".,;:").casefold() if doi else None,
            "title": title, "title_key": title_key,
            "own_pmcid": pmcids[-1].casefold() if pmcids else None}


def direct_citation_matches(target_keys: dict, source_text: str) -> list[str]:
    haystack = normalized_text(source_text)
    matches = []
    for field in ("doi", "own_pmcid"):
        value = target_keys[field]
        if value and normalized_text(value) in haystack:
            matches.append(field)
    title = target_keys["title_key"]
    if len(title) >= 40 and len(title.split()) >= 6 and title in haystack:
        matches.append("exact_title")
    return matches


def type_shapes(snapshot: dict) -> tuple[dict, dict]:
    graph = snapshot["graph"]
    validate_visible_dag(graph)
    knowledge = {item["knowledge_id"]: item for item in graph["knowledge"]}
    normalized = {item["id"]: item for item in normalize_map(snapshot)}
    node_to_knowledge = {node["id"]: node["knowledge_id"] for node in graph["nodes"]}
    catalog = {}
    block_types = {mode: {} for mode in MODES}
    for kid, item in knowledge.items():
        row = normalized[kid]
        base = {"kind": item["kind"], "knowledge_kind": item["knowledge_kind"]}
        coarse = f"{base['kind']}/{base['knowledge_kind']}"
        operators = sorted({PREDICATES.get(statement["predicate"], "unregistered")
                            for statement in row["statements"]})
        family_payload = {**base, "action_status": item["action_status"],
                          "logic": row["logic"], "operator_families": operators}
        family_type = f"operator_family:{fingerprint(family_payload)}"
        role_statements = []
        for statement in row["statements"]:
            scope = statement["scope"]
            role_statements.append({
                "operator_family": PREDICATES.get(statement["predicate"], "unregistered"),
                "roles": sorted(role["role"] for role in statement["roles"]),
                "negated": statement["negated"],
                "quantifier": scope["quantifier"],
                "modality": scope["modality"],
                "has_time": scope["time"] is not None,
                "has_conditions": bool(scope["conditions"]),
            })
        role_payload = {**family_payload, "statement_shapes": sorted(role_statements, key=fingerprint)}
        role_type = f"operator_roles:{fingerprint(role_payload)}"
        block_types["coarse"][kid] = coarse
        block_types["operator_family"][kid] = family_type
        block_types["operator_roles"][kid] = role_type
        catalog[coarse] = base
        catalog[family_type] = family_payload
        catalog[role_type] = role_payload

    transitions = {mode: [] for mode in MODES}
    for transition in graph["transitions"]:
        source_kids = [node_to_knowledge[node_id] for node_id in transition["sources"]]
        target_kid = node_to_knowledge[transition["target"]]
        if len(source_kids) > MAXIMUM_ARITY:
            continue
        for mode in MODES:
            transitions[mode].append(shape(
                [block_types[mode][kid] for kid in source_kids],
                block_types[mode][target_kid],
            ))
    return {"block_types": block_types, "transitions": transitions}, catalog


def shape(source_types: list[str], target_type: str) -> dict:
    return {"arity": len(source_types), "source_types": sorted(source_types), "target_type": target_type}


def shape_id(value: dict) -> str:
    return fingerprint(value)


def add_bit(support: dict[str, int], key: str, bit: int) -> None:
    support[key] = support.get(key, 0) | bit


def graph_supports(rows: list[dict], mode: str) -> tuple[dict[str, int], dict[str, dict]]:
    support: dict[str, int] = {}
    catalog = {}
    for index, row in enumerate(rows):
        bit = 1 << index
        for item in row["transitions"][mode]:
            key = shape_id(item)
            add_bit(support, key, bit)
            catalog[key] = item
    return support, catalog


def cooccurrence_supports(rows: list[dict], mode: str) -> tuple[dict[str, int], dict[str, dict]]:
    support: dict[str, int] = {}
    catalog = {}
    for index, row in enumerate(rows):
        counts = Counter(row["block_types"][mode].values())
        types = sorted(counts)
        bit = 1 << index
        for arity in range(1, MAXIMUM_ARITY + 1):
            for source_types in itertools.combinations_with_replacement(types, arity):
                needed = Counter(source_types)
                for target_type in types:
                    if all(counts[value] >= count for value, count in (needed + Counter({target_type: 1})).items()):
                        candidate = shape(list(source_types), target_type)
                        key = shape_id(candidate)
                        add_bit(support, key, bit)
                        catalog[key] = candidate
    return support, catalog


def candidate_support(support: dict[str, int], allowed_mask: int) -> dict[str, int]:
    result = {}
    for key, mask in support.items():
        count = (mask & allowed_mask).bit_count()
        if count >= MINIMUM_SUPPORT:
            result[key] = count
    return result


def score(selected: list[str], truth: list[dict]) -> dict:
    truth_counts = Counter(shape_id(item) for item in truth)
    truth_ids = set(truth_counts)
    selected_set = set(selected)
    hits = selected_set & truth_ids
    covered = sum(truth_counts[key] for key in hits)
    return {"predicted_shape_count": len(selected_set), "target_shape_count": len(truth_ids),
            "matched_shape_count": len(hits), "target_transition_count": len(truth),
            "covered_target_transition_count": covered,
            "precision": len(hits) / len(selected_set) if selected_set else 0.0,
            "recall": len(hits) / len(truth_ids) if truth_ids else 0.0,
            "transition_coverage": covered / len(truth) if truth else 0.0}


def ranked(support: dict[str, int], catalog: dict[str, dict], truth: list[dict]) -> dict:
    order = sorted(support, key=lambda key: (-support[key], key))
    return {str(k): {**score(order[:k], truth),
                     "selected": [{"shape": catalog[key], "publication_support": support[key]}
                                  for key in order[:k]]}
            for k in TOP_K}


def aggregate(folds: list[dict], mode: str, control: str, budget: str) -> dict:
    rows = [fold["scores"][mode][control][budget] for fold in folds]
    sums = {key: sum(row[key] for row in rows) for key in (
        "predicted_shape_count", "target_shape_count", "matched_shape_count",
        "target_transition_count", "covered_target_transition_count")}
    pairs = [(fold["scores"][mode]["graph"][budget]["matched_shape_count"],
              fold["scores"][mode]["cooccurrence"][budget]["matched_shape_count"])
             for fold in folds]
    return {**sums,
            "precision": sums["matched_shape_count"] / sums["predicted_shape_count"] if sums["predicted_shape_count"] else 0.0,
            "recall": sums["matched_shape_count"] / sums["target_shape_count"] if sums["target_shape_count"] else 0.0,
            "transition_coverage": sums["covered_target_transition_count"] / sums["target_transition_count"] if sums["target_transition_count"] else 0.0,
            "graph_wins": sum(a > b for a, b in pairs), "cooccurrence_wins": sum(a < b for a, b in pairs),
            "ties": sum(a == b for a, b in pairs), "fold_count": len(folds)}


def permutation_control(rows: list[dict], folds: list[dict], article_index: dict[str, int]) -> dict:
    observed = sum(fold["scores"]["operator_roles"]["graph"]["20"]["matched_shape_count"] for fold in folds)
    scores = []
    for permutation in range(PERMUTATION_COUNT):
        total_hits = 0
        for fold_number, fold in enumerate(folds):
            target_id = fold["target_article_id"]
            target_index = article_index[target_id]
            excluded = {item["article_id"] for item in fold["excluded_citations"]}
            allowed_ids = set(fold["training_article_ids"])
            support: dict[str, int] = {}
            catalog: dict[str, dict] = {}
            for article_id in sorted(allowed_ids):
                row = rows[article_index[article_id]]
                original = row["transitions"]["operator_roles"]
                targets = [item["target_type"] for item in original]
                rng = random.Random(PERMUTATION_SEED + permutation * len(folds) + fold_number * 7919 + article_index[article_id])
                rng.shuffle(targets)
                bit = 1 << article_index[article_id]
                for item, new_target in zip(original, targets):
                    changed = shape(item["source_types"], new_target)
                    key = shape_id(changed)
                    add_bit(support, key, bit)
                    catalog[key] = changed
            allowed_mask = sum(1 << article_index[item] for item in allowed_ids)
            current = candidate_support(support, allowed_mask)
            selected = sorted(current, key=lambda key: (-current[key], key))[:20]
            truth = rows[target_index]["transitions"]["operator_roles"]
            total_hits += score(selected, truth)["matched_shape_count"]
        scores.append(total_hits)
    ordered = sorted(scores)
    return {"permutation_count": PERMUTATION_COUNT, "seed": PERMUTATION_SEED,
            "observed_graph_matches_at_20": observed, "null_mean": mean(scores),
            "null_standard_deviation": pstdev(scores),
            "null_95th_percentile": ordered[math.ceil(.95 * len(ordered)) - 1],
            "null_maximum": ordered[-1],
            "empirical_one_sided_p": (1 + sum(item >= observed for item in scores)) / (PERMUTATION_COUNT + 1),
            "method_ru": "В каждой обучающей статье перемешивались типы целевых блоков между уже заданными группами предпосылок; арность, типы предпосылок, число переходов и частоты типов выводов сохранялись.",
            "interpretation_limit_ru": "Проверяется связь форм предпосылок с формами результатов, а не научная истинность и не вся видимая топология DAG.",
            "scores": scores}


def main():
    prohibit_generation()
    manifest = load_json(MANIFEST_PATH)
    seal = load_json(SEAL_PATH)
    source_manifest = Path(manifest["metadata"]["source_manifest_path"])
    sealed_predictions = TRAINING / "sealed" / seal["run_id"] / "predictions.json"
    require(seal["sealed"] and seal["training_count"] == 21, "Требуется проверенный seal корпуса из 21 источника")
    require(seal["source_manifest_sha256"] == file_sha(source_manifest), "Исходный манифест не совпадает с seal")
    require(seal["training_manifest_sha256"] == file_sha(MANIFEST_PATH), "Обучающий манифест не совпадает с seal")
    require(seal["prediction_sha256"] == fingerprint(load_json(sealed_predictions)), "Содержимое запечатанного прогноза изменилось")
    require(seal["target_map_read"] is False and seal["target_map_path_passed"] is False,
            "Карта отдельной целевой статьи была доступна обучающему запуску")
    require(seal["model_calls"] == 0, "Модельный вызов отмечен в seal")

    repository = FileForecastMaps(manifest["sources"])
    snapshots = []
    for entry in manifest["sources"]:
        ref = entry["reference"]
        item = repository.get(ref["article_id"], ref["pipeline_id"], repository.owner, ref["run_id"])
        require(item is not None, "Карта из allowlist не найдена")
        snapshots.append((item, entry))

    rows = []
    type_catalog = {}
    for snapshot, entry in snapshots:
        typed, catalog = type_shapes(snapshot)
        type_catalog.update(catalog)
        rows.append({"article_id": snapshot["article_id"], "run_id": snapshot["run_id"],
                     "source_sha256": snapshot["source"]["sha256"], "source_text": snapshot["source"]["text"],
                     "citation_keys": citation_keys(snapshot), "family": entry.get("family", snapshot["article_id"]),
                     **typed})
    require(len(rows) == 21 and len({row["article_id"] for row in rows}) == 21, "Ожидались 21 уникальная публикация")
    article_index = {row["article_id"]: index for index, row in enumerate(rows)}
    type_profile = {mode: {row["article_id"]: len(set(row["block_types"][mode].values())) for row in rows}
                    for mode in MODES}
    if "--profile-only" in sys.argv:
        print(json.dumps({mode: {"maximum": max(counts.values()), "median": sorted(counts.values())[len(counts) // 2],
                                 "per_article": counts} for mode, counts in type_profile.items()},
                         ensure_ascii=False, indent=2))
        return

    # Предварительно строим структуры для всех трёх видов представления.
    graph_support = {}
    graph_catalog = {}
    cooccur_support = {}
    cooccur_catalog = {}
    for mode in MODES:
        graph_support[mode], graph_catalog[mode] = graph_supports(rows, mode)
        cooccur_support[mode], cooccur_catalog[mode] = cooccurrence_supports(rows, mode)

    folds = []
    for target_index, target in enumerate(rows):
        excluded_citations = []
        for source_index, source in enumerate(rows):
            if source_index == target_index:
                continue
            matches = direct_citation_matches(target["citation_keys"], source["source_text"])
            if matches:
                excluded_citations.append({"article_id": source["article_id"], "evidence": matches})
        excluded_ids = {target["article_id"], *(item["article_id"] for item in excluded_citations)}
        training_ids = {row["article_id"] for row in rows} - excluded_ids
        allowed_mask = sum(1 << article_index[item] for item in training_ids)
        fold_scores = {}
        fold_predictions = {}
        truth_by_mode = target["transitions"]
        for mode in MODES:
            graph_candidates = candidate_support(graph_support[mode], allowed_mask)
            noedge_candidates = candidate_support(cooccur_support[mode], allowed_mask)
            fold_scores[mode] = {
                "graph": ranked(graph_candidates, graph_catalog[mode], truth_by_mode[mode]),
                "cooccurrence": ranked(noedge_candidates, cooccur_catalog[mode], truth_by_mode[mode]),
            }
            fold_predictions[mode] = {
                "graph_candidate_count": len(graph_candidates),
                "cooccurrence_candidate_count": len(noedge_candidates),
            }
        folds.append({"target_article_id": target["article_id"], "target_title": target["citation_keys"]["title"],
                      "target_run_id": target["run_id"], "target_source_sha256": target["source_sha256"],
                      "training_article_ids": sorted(training_ids), "training_count": len(training_ids),
                      "excluded_citations": excluded_citations,
                      "target_transition_count": {mode: len(truth_by_mode[mode]) for mode in MODES},
                      "scores": fold_scores, "candidate_counts": fold_predictions})

    summaries = {}
    for mode in MODES:
        summaries[mode] = {"graph": {budget: aggregate(folds, mode, "graph", budget) for budget in map(str, TOP_K)},
                           "cooccurrence": {budget: aggregate(folds, mode, "cooccurrence", budget) for budget in map(str, TOP_K)}}
    paired = {}
    for mode in MODES:
        paired[mode] = {}
        for budget in map(str, TOP_K):
            wins = losses = ties = graph_hits = cooccur_hits = 0
            for fold in folds:
                graph_hits_fold = fold["scores"][mode]["graph"][budget]["matched_shape_count"]
                cooccur_hits_fold = fold["scores"][mode]["cooccurrence"][budget]["matched_shape_count"]
                graph_hits += graph_hits_fold; cooccur_hits += cooccur_hits_fold
                wins += graph_hits_fold > cooccur_hits_fold
                losses += graph_hits_fold < cooccur_hits_fold
                ties += graph_hits_fold == cooccur_hits_fold
            paired[mode][budget] = {"graph_hits": graph_hits, "cooccurrence_hits": cooccur_hits,
                                    "graph_wins": wins, "cooccurrence_wins": losses, "ties": ties}

    permutation = permutation_control(rows, folds, article_index)
    result = {
        "audit_version": "operator-family-transition-lopo-training21-1",
        "training_manifest_sha256": file_sha(MANIFEST_PATH),
        "source_manifest_sha256": file_sha(source_manifest),
        "forecast_parent_run_id": seal["run_id"],
        "forecast_parent_sha256": seal["prediction_sha256"],
        "source_count": len(rows), "minimum_publication_support": MINIMUM_SUPPORT,
        "maximum_transition_arity": MAXIMUM_ARITY, "top_k": list(TOP_K),
        "normalizer_version": "schema6-normalizer-4", "operator_routing_version": ROUTING_VERSION,
        "operator_routing_dictionary_sha256": ROUTING_SHA256,
        "type_definitions": {
            "coarse": "kind/knowledge_kind",
            "operator_family": "kind/knowledge_kind + action_status + frame logic + explicit operator-family multiset; unregistered predicates share one label",
            "operator_roles": "operator-family type + per-statement role names, negation, quantifier, modality and presence of time/conditions",
        },
        "mode_summaries": summaries, "paired_comparison": paired,
        "permutation_control_operator_roles": permutation,
        "folds": folds, "type_catalog": type_catalog,
        "model_calls": 0, "network_calls": 0,
        "scientific_content_prediction": False,
        "interpretation_ru": "Сравниваются только повторяемые формы переходов, не предсказываются новые научные факты."}

    OUTPUT.mkdir(parents=True, exist_ok=True)
    data_path = OUTPUT / "data.json"
    data_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = [
        "# Удержанный прогноз форм переходов с семействами операторов",
        "",
        "Это LOPO-проверка 21 карты: в каждом фолде карта цели исключена, а прямые цитаторы удалены из обучения. Результат относится к структурным формам переходов, а не к новому научному содержанию.",
        "",
        f"- Источников: {len(rows)}; минимальная поддержка: {MINIMUM_SUPPORT} публикации; максимум предпосылок: {MAXIMUM_ARITY}.",
        f"- Роутер операторов: `{ROUTING_VERSION}`, словарь `{ROUTING_SHA256}`.",
        f"- Модельных и сетевых вызовов: 0; target-карта PMC10002471 в этом тесте не использовалась.",
        "",
        "## Результаты при равном бюджете",
        "",
        "| Представление | Режим | @20 попаданий / выдано | Точность | Полнота | Фолды: выигрыш графа / контроль / ничья |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for mode in MODES:
        labels = {"coarse": "Вид знания", "operator_family": "Семейства операторов", "operator_roles": "Семейства + роли/логика"}
        for route in ("graph", "cooccurrence"):
            summary = summaries[mode][route]["20"]
            paired_row = paired[mode]["20"]
            wins = f"{paired_row['graph_wins']} / {paired_row['cooccurrence_wins']} / {paired_row['ties']}" if route == "graph" else "—"
            report.append(f"| {labels[mode]} | {'Связи графа' if route == 'graph' else 'Совместная встречаемость'} | {summary['matched_shape_count']} / {summary['predicted_shape_count']} | {summary['precision']:.3f} | {summary['recall']:.3f} | {wins} |")
    report += [
        "",
        "## Перестановочный контроль",
        "",
        f"На представлении «семейства + роли/логика» наблюдалось {permutation['observed_graph_matches_at_20']} попаданий при @20. После {PERMUTATION_COUNT} перестановок соответствия типов предпосылок и выводов среднее — {permutation['null_mean']:.2f}, 95-й процентиль — {permutation['null_95th_percentile']}, максимум — {permutation['null_maximum']}; эмпирическая односторонняя p-оценка — {permutation['empirical_one_sided_p']:.4f}.",
        "",
        permutation["method_ru"],
        permutation["interpretation_limit_ru"],
        "",
        "## Интерпретация",
        "",
        "Семейства операторов здесь обобщают форму блока; режим с ролями и логическими признаками проверяет, сохраняется ли перенос после добавления части скрытой семантики. Даже выигрыш графа означает только, что конкретные типы предпосылок помогают предсказать тип перехода. Он не показывает совпадение предикатов, участников, чисел или условий и не является силлогизмом.",
        "",
        "Все карты исходного корпуса ранее были прочитаны при подготовке эксперимента, поэтому это ретроспективная LOPO-диагностика, а не проспективный слепой опыт. Пересечение участников когорт, транзитивное цитирование и экспертная корректность карт полностью не установлены.",
        "",
        "## Воспроизводимость",
        "",
        f"Родительский запечатанный прогон: `{seal['run_id']}`. SHA-256: `{seal['prediction_sha256']}`. Обучающий манифест: `{file_sha(MANIFEST_PATH)}`.",
        "Модели и сеть не использовались. Исходные карты, прошлые прогнозы и UI не изменялись.",
    ]
    report_path = OUTPUT / "report.ru.md"
    report_path.write_text("\n".join(report) + "\n", encoding="utf-8")
    receipt = {"audit_version": result["audit_version"], "builder_sha256": file_sha(Path(__file__)),
               "files": {name: file_sha(OUTPUT / name) for name in ("data.json", "report.ru.md")},
               "parent_seal_verified": True, "target_map_read": False,
               "model_calls": 0, "network_calls": 0}
    (OUTPUT / "verification.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"mode_summaries": summaries, "paired_comparison": paired,
                      "permutation": {key: value for key, value in permutation.items() if key != "scores"}},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

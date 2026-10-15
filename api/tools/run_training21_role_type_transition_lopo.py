"""Проверяет перенос форм переходов с заранее заданными типами общих ролей."""
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
from domain.operation_role_bindings import ROLE_TYPES
from infrastructure.free_prediction_snapshots import FileForecastMaps
from tools import run_training21_operator_transition_lopo as baseline

BASE = ROOT / "eval" / "whole_map_forecast" / "research-corpus-extension-v1" / "pmc10002471-codex-map-v1"
TRAINING = BASE / "training21"
MANIFEST_PATH = TRAINING / "training-corpus-manifest.json"
SEAL_PATH = TRAINING / "seal-receipt.json"
OUTPUT = ROOT / "eval" / "whole_map_forecast" / "operator-role-type-transition-lopo-v1" / "training21"
MODE = "role_types"
PERMUTATIONS = 1000
SEED = 20261015
IMPLEMENTATION = (
    Path(__file__),
    Path(__file__).with_name("run_training21_operator_transition_lopo.py"),
    ROOT / "api" / "domain" / "operation_role_bindings.py",
)


def file_sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def role_type(role: str) -> str:
    # Неизвестные имена ролей остаются точными и не превращаются в wildcard.
    return ROLE_TYPES.get(role, role)


def role_type_shapes(typed: dict, catalog: dict) -> tuple[dict, dict, Counter]:
    old_to_new = {}
    new_catalog = {}
    mapped_counts = Counter()
    for old_id, payload in catalog.items():
        if not old_id.startswith("operator_roles:"):
            continue
        transformed = json.loads(json.dumps(payload, ensure_ascii=False))
        for statement in transformed["statement_shapes"]:
            original_roles = statement["roles"]
            statement["roles"] = sorted({role_type(role) for role in original_roles})
        new_id = "operator_role_types:" + fingerprint(transformed)
        old_to_new[old_id] = new_id
        new_catalog[new_id] = transformed
    require(old_to_new, "Нет типов операторов с ролями")
    block_types = {}
    for knowledge_id, old_id in typed["block_types"]["operator_roles"].items():
        require(old_id in old_to_new, "Неизвестен тип блока с ролями")
        block_types[knowledge_id] = old_to_new[old_id]
        for statement in catalog[old_id]["statement_shapes"]:
            mapped_counts.update(role for role in statement["roles"] if role in ROLE_TYPES)
    transitions = []
    for item in typed["transitions"]["operator_roles"]:
        require(item["target_type"] in old_to_new
                and all(source in old_to_new for source in item["source_types"]),
                "Неизвестен тип предпосылки или результата")
        transitions.append(baseline.shape(
            [old_to_new[source] for source in item["source_types"]],
            old_to_new[item["target_type"]],
        ))
    return {"block_types": {MODE: block_types}, "transitions": {MODE: transitions}}, new_catalog, mapped_counts


def permutation_control(rows: list[dict], folds: list[dict], article_index: dict[str, int]) -> dict:
    observed = sum(fold["scores"][MODE]["graph"]["20"]["matched_shape_count"] for fold in folds)
    scores = []
    for permutation in range(PERMUTATIONS):
        total_hits = 0
        for fold_number, fold in enumerate(folds):
            target_index = article_index[fold["target_article_id"]]
            allowed_ids = set(fold["training_article_ids"])
            support = {}
            catalog = {}
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
            current = baseline.candidate_support(support, allowed_mask)
            selected = sorted(current, key=lambda key: (-current[key], key))[:20]
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
    require(not OUTPUT.exists(), "Выходная папка существует; неизменяемый прогон не перезаписывается")
    baseline.prohibit_generation()
    manifest = load_json(MANIFEST_PATH)
    seal = load_json(SEAL_PATH)
    source_manifest = Path(manifest["metadata"]["source_manifest_path"])
    sealed_predictions = TRAINING / "sealed" / seal["run_id"] / "predictions.json"
    require(seal["sealed"] and seal["training_count"] == 21, "Требуется seal корпуса из 21 источника")
    require(seal["source_manifest_sha256"] == file_sha(source_manifest)
            and seal["training_manifest_sha256"] == file_sha(MANIFEST_PATH),
            "Хеши манифестов не совпадают с seal")
    require(seal["prediction_sha256"] == fingerprint(load_json(sealed_predictions))
            and seal["target_map_read"] is False and seal["target_map_path_passed"] is False
            and seal["model_calls"] == 0,
            "Родительский прогноз не прошёл проверку seal")

    repository = FileForecastMaps(manifest["sources"])
    rows = []
    type_catalog = {}
    mapped_role_counts = Counter()
    source_records = []
    for entry in manifest["sources"]:
        ref = entry["reference"]
        snapshot = repository.get(ref["article_id"], ref["pipeline_id"], repository.owner, ref["run_id"])
        require(snapshot is not None, "Карта из явного обучающего списка не найдена")
        typed, catalog = baseline.type_shapes(snapshot)
        transformed, local_catalog, mapped = role_type_shapes(typed, catalog)
        type_catalog.update(local_catalog)
        mapped_role_counts.update(mapped)
        rows.append({
            "article_id": snapshot["article_id"],
            "citation_keys": baseline.citation_keys(snapshot),
            "source_text": snapshot["source"]["text"],
            "block_types": transformed["block_types"],
            "transitions": transformed["transitions"],
        })
        source_records.append({
            "article_id": snapshot["article_id"],
            "run_id": snapshot["run_id"],
            "source_sha256": snapshot["source"]["sha256"],
            "map_sha256": entry["file_sha256"],
            "graph_sha256": entry["graph_sha256"],
        })
    require(len(rows) == 21 and len({row["article_id"] for row in rows}) == 21,
            "Ожидались 21 уникальный источник")

    graph_support, graph_catalog = baseline.graph_supports(rows, MODE)
    cooccur_support, cooccur_catalog = baseline.cooccurrence_supports(rows, MODE)
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
        noedge_candidates = baseline.candidate_support(cooccur_support, allowed_mask)
        truth = target["transitions"][MODE]
        folds.append({
            "target_article_id": target["article_id"],
            "target_title": target["citation_keys"]["title"],
            "target_transition_count": len(truth),
            "training_article_ids": sorted(training_ids),
            "training_count": len(training_ids),
            "excluded_citations": excluded_citations,
            "scores": {
                MODE: {
                    "graph": baseline.ranked(graph_candidates, graph_catalog, truth),
                    "cooccurrence": baseline.ranked(noedge_candidates, cooccur_catalog, truth),
                }
            },
        })

    summaries = {route: {
        budget: baseline.aggregate(folds, MODE, route, budget) for budget in map(str, baseline.TOP_K)
    } for route in ("graph", "cooccurrence")}
    paired = {}
    for budget in map(str, baseline.TOP_K):
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
        "audit_version": "operator-role-type-transition-lopo-training21-1",
        "parent_seal_run_id": seal["run_id"],
        "parent_prediction_sha256": seal["prediction_sha256"],
        "training_manifest_sha256": file_sha(MANIFEST_PATH),
        "source_manifest_sha256": file_sha(source_manifest),
        "source_count": len(rows),
        "source_records": source_records,
        "minimum_publication_support": baseline.MINIMUM_SUPPORT,
        "maximum_transition_arity": baseline.MAXIMUM_ARITY,
        "top_k": list(baseline.TOP_K),
        "parent_operator_routing_version": baseline.ROUTING_VERSION,
        "parent_operator_routing_sha256": baseline.ROUTING_SHA256,
        "role_taxonomy_version": "source-bound-operation-role-bindings-1",
        "role_taxonomy_sha256": fingerprint(ROLE_TYPES),
        "role_types": ROLE_TYPES,
        "role_mapping_policy": "Известные общие роли сводятся к типам; неизвестные роли сохраняются дословно.",
        "mapped_role_occurrences": sum(mapped_role_counts.values()),
        "distinct_mapped_role_labels": dict(sorted(mapped_role_counts.items())),
        "mode_definition": "Семейство оператора, типизированные общие роли, точные неизвестные роли, логика, отрицание, квантор, модальность, наличие времени и условий.",
        "summaries": summaries,
        "paired_comparison": paired,
        "permutation_control": {key: value for key, value in permutation.items() if key != "scores"},
        "folds": folds,
        "type_catalog": type_catalog,
        "model_calls": 0,
        "network_calls": 0,
        "target_map_read": False,
        "scientific_content_prediction": False,
    }

    report = [
        "# Проверка переноса после типизации общих ролей",
        "",
        "Это удержанная LOPO-проверка 21 карты. Целевая карта и найденные прямые цитаторы исключаются из обучения в каждом фолде. Проверяется только перенос формы переходов; научные утверждения и их истинность не предсказываются.",
        "",
        f"- Источников: {len(rows)}; минимальная поддержка: {baseline.MINIMUM_SUPPORT} публикации; максимум предпосылок: {baseline.MAXIMUM_ARITY}.",
        f"- Родительский запечатанный прогноз: {seal['run_id']}; целевая карта PMC10002471 не использовалась.",
        f"- Типизация ролей: source-bound-operation-role-bindings-1; хеш словаря {fingerprint(ROLE_TYPES)}.",
        f"- Явно типизированных вхождений ролей: {sum(mapped_role_counts.values())}; неизвестные роли оставлены точными.",
        "- Модельных и сетевых вызовов: 0.",
        "",
        "## Результаты при одинаковом бюджете",
        "",
        "| Лимит | Граф: совпало / выдано | Без рёбер: совпало / выдано | Выигрыш графа / контроля / ничья по фолдам |",
        "|---:|---:|---:|---:|",
    ]
    for budget in map(str, baseline.TOP_K):
        graph = summaries["graph"][budget]
        control = summaries["cooccurrence"][budget]
        comparison = paired[budget]
        report.append(
            f"| @{budget} | {graph['matched_shape_count']} / {graph['predicted_shape_count']} | "
            f"{control['matched_shape_count']} / {control['predicted_shape_count']} | "
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
        "Переставлялись типы выводов внутри переходов каждой статьи при сохранении предпосылок, арности и числа переходов.",
        "",
        "## Интерпретация",
        "",
        "Типизация снимает только буквальное расхождение заранее перечисленных общих имён ролей. Предикаты, участники, значения, модальность, отрицание, наличие времени и условий остаются раздельными. Неизвестные роли не становятся универсальными подстановками.",
        "",
        "Даже рост совпадений означает только перенос схемы перехода. Для проверки свободного прогноза содержания потребуются замороженные содержательные кандидаты и оценка по исходным фрагментам цели.",
        "",
        "Все карты корпуса были известны до аудита. Это ретроспективная LOPO-диагностика, не перспективная слепая проверка. Прямые цитаторы исключены, но независимость когорт и экспертная правильность карт не установлены.",
        "",
        "## Воспроизводимость",
        "",
        f"Обучающий манифест: {file_sha(MANIFEST_PATH)}. Хеш словаря ролей: {fingerprint(ROLE_TYPES)}.",
        "Исходные карты и прежние прогнозы не изменялись.",
    ]
    report_raw = ("\n".join(report) + "\n").encode("utf-8")
    data_raw = (json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    manifest_raw = MANIFEST_PATH.read_bytes()
    taxonomy_raw = (json.dumps(ROLE_TYPES, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")

    write_new(OUTPUT / "training-corpus-manifest.json", manifest_raw)
    write_new(OUTPUT / "role-taxonomy.json", taxonomy_raw)
    for path in IMPLEMENTATION:
        write_new(OUTPUT / "implementation" / path.relative_to(ROOT), path.read_bytes())
    write_new(OUTPUT / "data.json", data_raw)
    write_new(OUTPUT / "report.ru.md", report_raw)
    receipt = {
        "audit_version": result["audit_version"],
        "implementation_sha256": {str(path.relative_to(ROOT)): file_sha(path) for path in IMPLEMENTATION},
        "artifacts_sha256": {
            "training-corpus-manifest.json": file_sha(OUTPUT / "training-corpus-manifest.json"),
            "role-taxonomy.json": file_sha(OUTPUT / "role-taxonomy.json"),
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
            "Хеш отчёта не совпал после записи")
    print(json.dumps({"summaries": summaries, "paired": paired,
                      "permutation": receipt["artifacts_sha256"],
                      "output": str(OUTPUT)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

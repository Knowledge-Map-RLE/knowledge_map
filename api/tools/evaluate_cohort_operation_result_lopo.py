"""Оценивает usage=result фолды после проверки всех прогнозных печатей."""
from __future__ import annotations

import json
from collections import defaultdict
from hashlib import sha256
from pathlib import Path

from domain.article_maps import require
from domain.cohort_operation_result_transfer import extract_map
from domain.cohort_operation_transfer import extract_map as extract_all_usage_map
from domain.cohort_operation_transfer import score
from domain.sealed_operation_result_forecast import VERSION
from infrastructure.immutable_files import write_immutable
from tools.run_free_prediction import disable_network

ROOT = Path(r"D:\Knowledge_Map")
BASE = ROOT / "eval/whole_map_forecast/cohort_operation_prediction/result-usage-lopo-v1"
MANIFEST = BASE / "source-manifest.json"
OPERATION_RU = {
    "incidence_estimation": "оценка частоты новых случаев",
    "person_time_calculation": "расчёт человеко-времени",
    "survival_model_fitting": "подгонка модели времени до события",
}
OUTPUT_RU = {
    "reported_association": "сообщаемая ассоциация",
    "reported_frequency": "сообщаемая частота",
    "reported_model_parameter": "параметр статистической модели",
}
MODES = ("same_article_cooccurrence", "dependency_edges_all_usage", "dependency_edges_result_usage")
MODE_RU = {
    "same_article_cooccurrence": "Совместная встречаемость без связей",
    "dependency_edges_all_usage": "Любые прямые связи",
    "dependency_edges_result_usage": "Только связи usage=result",
}


def _sha(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def _json_bytes(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")


def _label_pairs(pairs: list[list[str]]) -> str:
    return "; ".join(f"{OPERATION_RU.get(a, a)} → {OUTPUT_RU.get(b, b)}" for a, b in pairs) or "—"


def _render_report(result: dict) -> str:
    rows = []
    for fold in result["folds"]:
        scores = fold["modes"]
        if not fold["scored"]:
            rows.append(
                f"| {fold['target_article_id']} | — | не оценено | не оценено | не оценено: нет явной метки `result` |"
            )
            continue
        rows.append(
            f"| {fold['target_article_id']} | {_label_pairs(fold['target_pairs'])} | "
            f"{scores['same_article_cooccurrence']['hits']}/{scores['same_article_cooccurrence']['predicted_count']} | "
            f"{scores['dependency_edges_all_usage']['hits']}/{scores['dependency_edges_all_usage']['predicted_count']} | "
            f"{scores['dependency_edges_result_usage']['hits']}/{scores['dependency_edges_result_usage']['predicted_count']} |"
        )
    lines = [
        "# Повторная проверка «операция → категория результата» с фильтром метки перехода",
        "",
        "**Это диагностика типов результата, не прогноз научного факта.** Повторяется ранее запечатанный LOPO-опыт на тех же картах и тех же известных методах. В оценку входят только целевые пары с явной меткой `usage=result`; остальные целевые переходы считаются неразмеченными, а не отрицательными примерами.",
        "",
        "## Режимы и общий результат",
        "",
        f"Оценены {result['scored_fold_count']} из {result['fold_count']} целей; у {result['unscored_target_count']} целей нет явной разметки `usage=result`.",
        "",
        "| Режим | Совпало / кандидатов | Истинных пар | Точность | Полнота |",
        "|---|---:|---:|---:|---:|",
    ]
    for mode in MODES:
        summary = result["aggregate"][mode]
        precision = f"{summary['precision']:.3f}" if summary["precision"] is not None else "—"
        recall = f"{summary['recall']:.3f}" if summary["recall"] is not None else "—"
        lines.append(
            f"| {MODE_RU[mode]} | {summary['hits']}/{summary['predicted']} | "
            f"{summary['target']} | {precision} | {recall} |"
        )
    lines.extend([
        "",
        "## По удержанным статьям",
        "",
        "| Цель | Фактические пары `usage=result` | Без рёбер | Все типы рёбер | Только `result` |",
        "|---|---|---:|---:|---:|",
        *rows,
        "",
        "## Согласованность меток",
        "",
        "| Пара «операция → категория» | Переходов по метке | Публикаций по метке |",
        "|---|---|---|",
    ])
    for item in result["usage_distribution"]:
        counts = ", ".join(f"{usage}: {count}" for usage, count in sorted(item["usage_counts"].items()))
        sources = ", ".join(f"{usage}: {len(article_ids)}" for usage, article_ids in sorted(item["article_ids_by_usage"].items()))
        pair = _label_pairs([[item["operation_family"], item["output_family"]]])
        lines.append(f"| {pair} | {counts} | {sources} |")
    lines.extend([
        "",
        "## Вывод",
        "",
        "В одинаковой паре «операция → категория» метки расходятся между картами: одна и та же пара бывает помечена как `result`, `method`, `data` или `premise`. Поэтому фильтр только `result` не набирает минимальную поддержку двух источников после удержания цели. На двух размеченных целях широкий режим даёт 4/4, а режим без связей — 4/12; три остальные цели остаются неоценёнными. Это предварительный сигнал полезности структуры для классификации вида результата, но семантика обучающих меток ещё не согласована.",
        "",
        "Дальше нужно проверить и согласовать разметку `usage` по полным обоснованиям переходов, затем повторить прогноз с тем же минимумом поддержки на новых удержанных статьях. Даже подтверждённое улучшение классификации не будет прогнозом нового научного содержания: для этого нужны операторы, которые выводят направление или тип результата при сохранении популяции, исхода, единиц, сроков, дизайна и статистических ограничений.",
        "",
        f"Пять прогнозов сформированы и запечатаны до чтения целевых карт. Поддержка — не менее двух публикаций. В обучении 16 карт; целевая PMC10000452 исключена. Модельных и сетевых вызовов — 0. Экспертная научная проверка не проводилась. Версия: `{result['protocol']}`; хеш манифеста: `{result['source_manifest_sha256']}`.",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    disable_network()
    manifest_raw = MANIFEST.read_bytes()
    manifest = json.loads(manifest_raw)
    sources = {row["article_id"]: row for row in manifest["sources"]}
    input_paths = sorted(path for path in (BASE / "inputs").glob("*.json") if path.name != "index.json")
    require(len(sources) == 16 and len(input_paths) == 5, "Ожидались 16 карт и 5 целевых фолдов")

    sealed = []
    for input_path in input_paths:
        input_raw = input_path.read_bytes()
        fold_input = json.loads(input_raw)
        target_id = fold_input["target"]["article_id"]
        require(fold_input["source_manifest_sha256"] == _sha(manifest_raw),
                "Манифест фолда отличается")
        require(target_id in sources and target_id not in {
            row["article_id"] for row in fold_input["training_sources"]}, "Цель утекла в обучение")
        prediction_paths = list((BASE / "runs" / target_id).glob("*/sealed-prediction.json"))
        require(len(prediction_paths) == 1, f"Для {target_id} нужен один запечатанный прогноз")
        prediction_path = prediction_paths[0]
        run_root = prediction_path.parent
        prediction_raw = prediction_path.read_bytes()
        seal_raw = (run_root / "seal.json").read_bytes()
        prediction, seal = json.loads(prediction_raw), json.loads(seal_raw)
        require(seal.get("sealed") is True and seal.get("protocol") == VERSION,
                "Прогноз не запечатан по актуальному контракту")
        require(seal.get("target_article_id") == target_id and seal.get("run_id") == run_root.name,
                "Идентификатор или квитанция не совпадают")
        require(seal.get("prediction_sha256") == _sha(prediction_raw), "Хеш запечатанного прогноза неверен")
        require(seal.get("input_sha256") == _sha(input_raw) == prediction.get("input_sha256"),
                "Хеш очищенного входа неверен")
        require(prediction.get("source_manifest_sha256") == _sha(manifest_raw),
                "Прогноз связан с другим манифестом")
        require(prediction.get("target_outputs_or_edges_available_to_forecaster") is False,
                "Целевые исходы были доступны прогнозчику")
        require(prediction.get("training_source_ids") == sorted(
            row["article_id"] for row in fold_input["training_sources"]), "Состав обучения отличается")
        require(set(prediction.get("forecasts", {})) == set(MODES), "Набор режимов изменился")
        sealed.append({"input": fold_input, "input_raw": input_raw, "prediction": prediction,
                       "prediction_raw": prediction_raw, "seal_raw": seal_raw,
                       "run_id": run_root.name})

    # Все прогнозы и квитанции проверены до чтения любого целевого графа.
    usage_totals = defaultdict(lambda: {
        "transition_count": 0,
        "usage_counts": defaultdict(int),
        "article_ids_by_usage": defaultdict(set),
    })
    for source_row in sources.values():
        source_raw = Path(source_row["map_path"]).read_bytes()
        require(_sha(source_raw) == source_row["map_sha256"], "Карта источника изменилась")
        source_map = json.loads(source_raw)
        source_extracted = extract_all_usage_map(source_map)
        for pair in source_extracted["graph_links"]:
            pair_key = "|".join(pair)
            for evidence in source_extracted["graph_evidence"][pair_key]:
                totals_for_pair = usage_totals[tuple(pair)]
                totals_for_pair["transition_count"] += 1
                totals_for_pair["usage_counts"][evidence["usage"]] += 1
                totals_for_pair["article_ids_by_usage"][evidence["usage"]].add(source_row["article_id"])

    folds = []
    totals = {mode: {"predicted": 0, "target": 0, "hits": 0} for mode in MODES}
    for item in sealed:
        prediction = item["prediction"]
        target_id = prediction["target_article_id"]
        source_row = sources[target_id]
        target_raw = Path(source_row["map_path"]).read_bytes()
        require(_sha(target_raw) == source_row["map_sha256"] == prediction["target_map_sha256"],
                "Целевая карта изменилась")
        target = json.loads(target_raw)
        strict = extract_map(target)
        broad = extract_all_usage_map(target)
        truth = {tuple(pair) for pair in strict["graph_links"]}
        broad_pairs = {tuple(pair) for pair in broad["graph_links"]}
        require(truth <= broad_pairs, "Строгий результат не является подмножеством исходных связей")
        scored_fold = bool(truth)
        mode_scores = None
        if scored_fold:
            mode_scores = {}
            for mode in MODES:
                candidates = {(row["operation_family"], row["output_family"])
                              for row in prediction["forecasts"][mode]}
                scored = score(candidates, truth)
                mode_scores[mode] = scored
                for field in ("predicted_count", "target_count", "hits"):
                    key = {"predicted_count": "predicted", "target_count": "target", "hits": "hits"}[field]
                    totals[mode][key] += scored[field]
        usage_by_pair = {
            "|".join(pair): sorted({row["usage"] for row in broad["graph_evidence"]["|".join(pair)]})
            for pair in sorted(broad_pairs)
        }
        folds.append({
            "target_article_id": target_id,
            "target_run_id": prediction["target_run_id"],
            "sealed_run_id": item["run_id"],
            "target_operations": prediction["known_operation_families"],
            "scored": scored_fold,
            "unscored_reason": None if scored_fold else "target_has_no_explicit_result_usage_link",
            "target_pairs": [list(pair) for pair in sorted(truth)],
            "all_usage_only_target_pairs": [list(pair) for pair in sorted(broad_pairs - truth)],
            "usage_by_pair": usage_by_pair,
            "modes": mode_scores,
            "prediction_sha256": _sha(item["prediction_raw"]),
        })

    aggregate = {}
    for mode, row in totals.items():
        aggregate[mode] = {**row,
                           "precision": row["hits"] / row["predicted"] if row["predicted"] else None,
                           "recall": row["hits"] / row["target"] if row["target"] else None}
    result = {
        "protocol": VERSION,
        "source_manifest_sha256": _sha(manifest_raw),
        "minimum_publication_support": 2,
        "fold_count": len(folds),
        "scored_fold_count": sum(fold["scored"] for fold in folds),
        "unscored_target_count": sum(not fold["scored"] for fold in folds),
        "transition_usage_filter": "result",
        "aggregate": aggregate,
        "folds": folds,
        "usage_distribution": [
            {"operation_family": pair[0], "output_family": pair[1],
             "transition_count": row["transition_count"],
             "usage_counts": dict(row["usage_counts"]),
             "article_ids_by_usage": {usage: sorted(article_ids)
                                      for usage, article_ids in row["article_ids_by_usage"].items()}}
            for pair, row in sorted(usage_totals.items())
        ],
        "all_forecasts_sealed_before_target_graphs_read": True,
        "network_disabled": True,
        "external_llm_calls": 0,
        "local_llm_calls": 0,
        "embedding_calls": 0,
        "scientific_fact_forecast": False,
        "expert_validated": False,
    }
    result_raw = _json_bytes(result)
    run_id = _sha(result_raw)[:32]
    output = BASE / "evaluations" / run_id
    report_raw = _render_report(result).encode("utf-8")
    write_immutable(output / "evaluation.json", result_raw)
    write_immutable(output / "report.ru.md", report_raw)
    file_hashes = {name: _sha((output / name).read_bytes())
                   for name in ("evaluation.json", "report.ru.md")}
    write_immutable(output / "manifest.json", _json_bytes({
        "run_id": run_id, "files_sha256": file_hashes, "immutable": True,
        "network_disabled": True, "model_calls": 0,
    }))
    print(json.dumps({"run_id": run_id, "report": str(output / "report.ru.md"),
                      "aggregate": aggregate, "folds": len(folds),
                      "model_calls": 0, "network_disabled": True}, ensure_ascii=False))


if __name__ == "__main__":
    main()

"""Оценивает пять запечатанных LOPO-прогнозов категорий результатов."""
from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

from domain.article_maps import require
from domain.cohort_operation_transfer import extract_map, score
from infrastructure.immutable_files import write_immutable
from tools.run_free_prediction import disable_network

ROOT = Path(r"D:\Knowledge_Map")
BASE = ROOT / "eval/whole_map_forecast/cohort_operation_prediction/sealed-lopo-v1"
INPUTS = BASE / "inputs"
MANIFEST = ROOT / "eval/whole_map_forecast/research-corpus-extension-v1/cohort-operation-transfer-v7/source-manifest.json"
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


def _sha(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def _json_bytes(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")


def main() -> None:
    disable_network()
    manifest_raw = MANIFEST.read_bytes()
    manifest = json.loads(manifest_raw)
    source_rows = {row["article_id"]: row for row in manifest["sources"]}
    input_paths = sorted(path for path in INPUTS.glob("*.json") if path.name != "index.json")
    require(bool(input_paths), "Не найдены обезличенные входы фолдов")

    sealed_folds = []
    for input_path in input_paths:
        input_raw = input_path.read_bytes()
        fold_input = json.loads(input_raw)
        target_id = fold_input["target"]["article_id"]
        require(fold_input["source_manifest_sha256"] == _sha(manifest_raw),
                "Манифест отличается от замороженного входа")
        candidates = list((BASE / "runs" / target_id).glob("*/sealed-prediction.json"))
        require(len(candidates) == 1, f"Для {target_id} нужен ровно один запечатанный прогноз")
        prediction_path = candidates[0]
        run_root = prediction_path.parent
        prediction_raw = prediction_path.read_bytes()
        seal_raw = (run_root / "seal.json").read_bytes()
        prediction = json.loads(prediction_raw)
        seal = json.loads(seal_raw)
        require(seal.get("sealed") is True and seal.get("target_article_id") == target_id,
                "Квитанция запечатывания некорректна")
        require(seal.get("run_id") == run_root.name, "Run id квитанции не совпадает")
        require(seal.get("prediction_sha256") == _sha(prediction_raw), "Хеш прогноза не совпадает")
        require(seal.get("input_sha256") == _sha(input_raw) == prediction.get("input_sha256"),
                "Хеш очищенного входа не совпадает")
        require(prediction.get("target_article_id") == target_id, "Целевой id прогноза не совпадает")
        require(prediction.get("target_outputs_or_edges_available_to_forecaster") is False,
                "Целевые выходы были доступны генератору")
        require(prediction.get("target_map_sha256") == fold_input["target"]["map_sha256"],
                "Хеш целевой карты не совпадает с очищенным входом")
        require(set(prediction.get("training_source_ids", [])) ==
                {row["article_id"] for row in fold_input["training_sources"]},
                "Состав обучающего фолда отличается от зафиксированного")
        require(target_id in source_rows, "Цель не найдена в реестре")
        sealed_folds.append({"input": fold_input, "prediction": prediction,
                             "prediction_raw": prediction_raw, "seal_raw": seal_raw,
                             "run_root": run_root})

    # Цели читаются только после проверки и накопления квитанций всех пяти прогнозов.
    evaluated_folds = []
    for row in sealed_folds:
        prediction = row["prediction"]
        target_id = prediction["target_article_id"]
        target_row = source_rows[target_id]
        require(target_row["map_sha256"] == prediction["target_map_sha256"],
                "Целевая карта в реестре изменилась")
        target_raw = Path(target_row["map_path"]).read_bytes()
        require(_sha(target_raw) == target_row["map_sha256"], "Целевая карта изменилась после прогноза")
        target_map = json.loads(target_raw)
        actual = extract_map(target_map)
        actual_pairs = {tuple(pair) for pair in actual["graph_links"]}
        modes = {}
        for mode in ("same_article_cooccurrence", "dependency_edges"):
            forecast = {(item["operation_family"], item["output_family"])
                        for item in prediction["forecasts"][mode]}
            modes[mode] = score(forecast, actual_pairs)
        evaluated_folds.append({
            "target_article_id": target_id,
            "target_run_id": prediction["target_run_id"],
            "sealed_run_id": row["run_root"].name,
            "target_operations": prediction["known_operation_families"],
            "target_pairs": [list(pair) for pair in sorted(actual_pairs)],
            "modes": modes,
            "missed_graph_pairs": modes["dependency_edges"]["missed_pairs"],
            "prediction_sha256": _sha(row["prediction_raw"]),
        })

    aggregate = {}
    for mode in ("same_article_cooccurrence", "dependency_edges"):
        predicted = sum(fold["modes"][mode]["predicted_count"] for fold in evaluated_folds)
        targets = sum(fold["modes"][mode]["target_count"] for fold in evaluated_folds)
        hits = sum(fold["modes"][mode]["hits"] for fold in evaluated_folds)
        aggregate[mode] = {"predicted": predicted, "target": targets, "hits": hits,
                           "precision": hits / predicted if predicted else None,
                           "recall": hits / targets if targets else None}
    result = {
        "protocol": "sealed-method-conditioned-result-category-lopo-1",
        "source_manifest_sha256": _sha(manifest_raw),
        "minimum_publication_support": 2,
        "fold_count": len(evaluated_folds),
        "aggregate": aggregate,
        "folds": evaluated_folds,
        "all_predictions_sealed_before_any_target_evaluation": True,
        "network_disabled": True,
        "external_llm_calls": 0,
        "local_llm_calls": 0,
        "embedding_calls": 0,
        "scientific_fact_forecast": False,
        "expert_validated": False,
    }
    run_id = _sha(_json_bytes(result))[:32]
    run_root = BASE / "evaluations-ru-v3" / run_id
    result_raw = _json_bytes(result)
    report_raw = render_report(result).encode("utf-8")
    write_immutable(run_root / "evaluation.json", result_raw)
    write_immutable(run_root / "report.ru.md", report_raw)
    files = {name: _sha((run_root / name).read_bytes()) for name in ("evaluation.json", "report.ru.md")}
    write_immutable(run_root / "manifest.json", _json_bytes({"run_id": run_id,
                    "files_sha256": files, "immutable": True, "model_calls": 0,
                    "network_disabled": True}))
    print(json.dumps({"run_id": run_id, "report": str(run_root / "report.ru.md"),
                      "evaluation": str(run_root / "evaluation.json"),
                      "aggregate": aggregate, "fold_count": len(evaluated_folds)}, ensure_ascii=False))


def render_report(result: dict) -> str:
    totals = result["aggregate"]
    graph = totals["dependency_edges"]
    baseline = totals["same_article_cooccurrence"]
    rows = []
    for fold in result["folds"]:
        graph_score = fold["modes"]["dependency_edges"]
        base_score = fold["modes"]["same_article_cooccurrence"]
        truth = ", ".join(f"{OPERATION_RU.get(a, a)} → {OUTPUT_RU.get(b, b)}"
                           for a, b in fold["target_pairs"]) or "нет типизированных пар"
        operations = ", ".join(OPERATION_RU.get(value, value) for value in fold["target_operations"])
        rows.append(f"| {fold['target_article_id']} | {operations} | {truth} | "
                    f"{graph_score['hits']}/{graph_score['predicted_count']} | "
                    f"{base_score['hits']}/{base_score['predicted_count']} |")
    graph_precision = f"{graph['precision']:.3f}" if graph["precision"] is not None else "—"
    base_precision = f"{baseline['precision']:.3f}" if baseline["precision"] is not None else "—"
    graph_recall = f"{graph['recall']:.3f}" if graph["recall"] is not None else "—"
    base_recall = f"{baseline['recall']:.3f}" if baseline["recall"] is not None else "—"
    missed = [f"{fold['target_article_id']}: {OPERATION_RU.get(pair[0], pair[0])} → "
              f"{OUTPUT_RU.get(pair[1], pair[1])}"
              for fold in result["folds"] for pair in fold["missed_graph_pairs"]]
    misses = "; ".join(missed) if missed else "нет"
    return f"""# Запечатанная проверка переноса «метод → категория результата»

## Протокол

Пять отдельных прогнозов сформированы до раскрытия результатов каждой целевой карты. Каждый изолированный процесс получил только свой очищенный вход с типом метода и 15 обучающими картами; целевая карта отсутствовала среди входных путей этого процесса. После проверки пяти хешей все цели были открыты для оценки. Минимальная поддержка шаблона — **{result['minimum_publication_support']} разные публикации**.

Обучающий корпус: 16 карт схемы 6 из замороженного реестра. Это историческая ретроспективная диагностика: статьи и карты уже были известны в исследовательском процессе. Проверяется категория результата при известном методе, а не свободный прогноз конкретного научного открытия.

## Сводный результат

| Режим | Попадания / кандидаты | Истинные пары | Точность | Полнота |
|---|---:|---:|---:|---:|
| Совместная встречаемость без связей | {baseline['hits']}/{baseline['predicted']} | {baseline['target']} | {base_precision} | {base_recall} |
| Прямые зависимости карты | {graph['hits']}/{graph['predicted']} | {graph['target']} | {graph_precision} | {graph_recall} |

В сумме режим без рёбер: **{baseline['hits']} из {baseline['predicted']} кандидатов**; режим зависимостей: **{graph['hits']} из {graph['predicted']}**. Пропуски графового режима: {misses}.

## По целевым публикациям

| Целевая статья | Известный тип метода | Фактические типизированные пары | Граф: попадания/кандидаты | Без рёбер: попадания/кандидаты |
|---|---|---|---:|---:|
{chr(10).join(rows)}

## Интерпретация

Кандидат создаётся повторяющимся в обучающих картах шаблоном «операция → категория результата». Здесь проверяется графовая структура: она может убрать неподдержанные сочетания, которые остаются при совместной встречаемости. Например, модель Кокса чаще связана с параметром статистической модели, чем просто с любым типом результата в той же статье. Это **статистический структурный паттерн**, а не силлогизм, причинный закон или один из 24 классических силлогизмов.

Даже если точность графового режима выше, этот опыт не доказывает, что Карта Знаний способна предсказать новое содержание научной статьи: выход — общая категория блока, метод дан на входе, истинные типы заранее ограничены теми, что размечены в корпусе, а число независимых целевых карт мало. Он проверяет одно необходимое звено — добавляют ли видимые зависимости карты дополнительную избирательность относительно тех же карт без связей.

Следующий шаг к основной цели — применить такое же запечатывание к операторам над содержательными научными утверждениями и смысловыми структурами, затем сравнить подтверждённые новые выводы с результатами на тех же знаниях без связей карты, с простой частотной базой и с перемешанным графом. Для силлогизмов нужно отдельно проверять допустимость каждой формы и существование объектов; повтор известных закономерностей не засчитывать как новое знание.

Модельных вызовов, эмбеддингов и сетевых запросов — 0. Все прогнозы зафиксированы до оценки. Карты, GOLD и сервисы не изменены. Код и метаданные сохраняют хеши; научная точность разметки требует экспертной проверки.
"""


if __name__ == "__main__":
    main()

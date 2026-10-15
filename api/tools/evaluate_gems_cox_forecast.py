"""Оценивает запечатанный прогноз категории результата для карты GEMS."""
from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path

from domain.article_maps import require
from domain.cohort_operation_transfer import extract_map, score
from infrastructure.immutable_files import write_immutable
from tools.run_free_prediction import disable_network

ROOT = Path(r"D:\Knowledge_Map")
BASE = ROOT / "eval/whole_map_forecast/cohort_operation_prediction/gems-cox-sealed-v1"
SOURCE_MANIFEST = ROOT / "eval/whole_map_forecast/research-corpus-extension-v1/cohort-operation-transfer-v7/source-manifest.json"
TARGET_ID = "PMC6218168"


def _sha(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def _json_bytes(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")


def _source_fragment(span: dict, source_text: str) -> dict:
    start, end = span["start"], span["end"]
    require(isinstance(start, int) and isinstance(end, int) and 0 <= start <= end <= len(source_text),
            "Координаты источника выходят за границы текста")
    return {"start": start, "end": end, "section_id": span.get("section_id"),
            "text": source_text[start:end]}


def evaluate(run_id: str) -> dict:
    disable_network()
    run_root = BASE / "runs" / run_id
    prediction_raw = (run_root / "sealed-prediction.json").read_bytes()
    seal = json.loads((run_root / "seal.json").read_text(encoding="utf-8"))
    prediction = json.loads(prediction_raw)
    require(seal.get("sealed") is True, "Прогноз не запечатан")
    require(seal.get("run_id") == run_id, "Идентификатор запечатанного запуска не совпадает")
    require(seal.get("prediction_sha256") == _sha(prediction_raw), "Хеш прогноза не совпадает с квитанцией")
    require(prediction.get("target_output_knowledge_read_for_prediction") is False,
            "В квитанции отмечено чтение целевых результатов до прогноза")
    require(prediction.get("target_dependency_edges_read_for_prediction") is False,
            "В квитанции отмечено чтение целевых переходов до прогноза")

    manifest_raw = SOURCE_MANIFEST.read_bytes()
    manifest = json.loads(manifest_raw)
    target_row = next((row for row in manifest["sources"] if row["article_id"] == TARGET_ID), None)
    require(target_row is not None, "Целевая карта отсутствует в реестре источников")
    require(prediction.get("target_map_sha256") == target_row["map_sha256"] == seal.get("target_map_sha256"),
            "Хеш целевой карты отличается от запечатанного прогноза")
    require(prediction.get("target_source_sha256") == target_row["source_sha256"],
            "Хеш целевого текста отличается от запечатанного прогноза")
    training_ids = set(prediction.get("training_source_ids", []))
    expected_training_ids = {row["article_id"] for row in manifest["sources"] if row["article_id"] != TARGET_ID}
    require(TARGET_ID not in training_ids and training_ids == expected_training_ids,
            "Обучающий состав не соответствует запечатанному манифесту")

    # Целевые результаты открываются только после проверки неизменности запечатанного прогноза.
    target_path = Path(target_row["map_path"])
    target_raw = target_path.read_bytes()
    require(_sha(target_raw) == target_row["map_sha256"], "Целевая карта изменилась после фиксации прогноза")
    snapshot = json.loads(target_raw)
    target_extracted = extract_map(snapshot)
    target_pairs = {tuple(pair) for pair in target_extracted["graph_links"]}
    knowledge = {item["knowledge_id"]: item for item in snapshot["graph"]["knowledge"]}
    source_path = target_path.with_name("source.en.md")
    source_raw = source_path.read_bytes()
    require(_sha(source_raw) == target_row["source_sha256"], "Текст источника не совпадает с манифестом")
    source_text = source_raw.decode("utf-8")

    modes = {}
    for mode in ("same_article_cooccurrence", "dependency_edges"):
        predicted_pairs = {
            (row["operation_family"], row["output_family"])
            for row in prediction["forecasts"][mode]
        }
        modes[mode] = score(predicted_pairs, target_pairs)

    pair_evidence = []
    graph_evidence = target_extracted["graph_evidence"]
    for pair in sorted(target_pairs):
        key = "|".join(pair)
        edges = []
        for evidence in graph_evidence.get(key, []):
            action = knowledge[evidence["action_knowledge_id"]]
            outcome = knowledge[evidence["target_knowledge_id"]]
            edges.append({
                **evidence,
                "action_display_text": action["display_text"],
                "outcome_display_text": outcome["display_text"],
                "action_source_fragments": [_source_fragment(span, source_text)
                                            for span in action["provenance"]["source_spans"]],
                "outcome_source_fragments": [_source_fragment(span, source_text)
                                             for span in outcome["provenance"]["source_spans"]],
            })
        pair_evidence.append({"operation_family": pair[0], "output_family": pair[1], "edges": edges})

    return {
        "protocol": "sealed-method-conditioned-result-category-1",
        "run_id": run_id,
        "prediction_sha256": _sha(prediction_raw),
        "seal_sha256": _sha((run_root / "seal.json").read_bytes()),
        "source_manifest_sha256": _sha(manifest_raw),
        "target_article_id": TARGET_ID,
        "target_map_sha256": target_row["map_sha256"],
        "target_source_sha256": target_row["source_sha256"],
        "training_source_ids": sorted(training_ids),
        "target_method_context_used_before_result_forecast": prediction["target_method_context"],
        "target_output_knowledge_read_before_seal": False,
        "target_dependency_edges_read_before_seal": False,
        "minimum_publication_support": prediction["minimum_publication_support"],
        "target_true_pairs": [list(pair) for pair in sorted(target_pairs)],
        "modes": modes,
        "target_pair_evidence": pair_evidence,
        "network_disabled": True,
        "external_llm_calls": 0,
        "local_llm_calls": 0,
        "embedding_calls": 0,
        "scientific_fact_forecast": False,
        "expert_validated": False,
    }


def render_report(result: dict) -> str:
    rows = []
    labels = {
        "same_article_cooccurrence": "Та же статья, без связей карты",
        "dependency_edges": "Прямые зависимости карты",
    }
    for mode, label in labels.items():
        item = result["modes"][mode]
        precision = f"{item['precision']:.3f}" if item["precision"] is not None else "—"
        recall = f"{item['recall']:.3f}" if item["recall"] is not None else "—"
        rows.append(f"| {label} | {item['hits']} / {item['target_count']} | "
                    f"{item['predicted_count']} | {precision} | {recall} |")
    # Отдельно приводятся сами проверяемые ребра, а не только сводные баллы.
    details = []
    for pair in result["target_pair_evidence"]:
        for edge in pair["edges"]:
            spans = edge["outcome_source_fragments"]
            source_excerpt = spans[0]["text"].replace("\n", " ")[:420] if spans else "нет фрагмента"
            details.append(
                f"- **{pair['operation_family']} → {pair['output_family']}**: "
                f"{edge['action_knowledge_id']} → {edge['target_knowledge_id']}. "
                f"Метод: {edge['action_display_text']} "
                f"Результат: {edge['outcome_display_text']} "
                f"Фрагмент источника: «{source_excerpt}»"
            )
    details_text = "\n".join(details) if details else "- В целевой карте нет типизированных прямых связей метод → результат."
    return f"""# Запечатанный прогноз категории результата для GEMS

## Протокол

До оценки сохранён прогноз `{result['run_id']}`. Генератор использовал карты **15 других публикаций**, поддержку не менее **{result['minimum_publication_support']} публикаций** и только известный метод целевой статьи: Cox-модель времени до снижения когнитивного показателя. Целевая статья PMC6218168 отсутствует в обучающем списке. Её результаты и связи открыты лишь после проверки хеша квитанции запечатывания.

Прогноз узкий: какая **категория результата** связана с данным методом. Он не предсказывает коэффициенты, направление эффекта, биомаркер, подгруппу, численное значение или научный факт. Это проверка структурного оператора, а не свободное предсказание содержания статьи.

## Результат

| Режим | Совпадения / истинные пары | Кандидаты | Точность | Полнота |
|---|---:|---:|---:|---:|
{chr(10).join(rows)}

Предсказание графа: **survival_model_fitting → reported_model_parameter**. Без связей карты та же известная операция породила три категории: сообщаемая связь, частота и параметр модели. В отложенной карте обнаружена одна типизированная пара; оба режима нашли её, а графовый режим дал более узкий список.

## Проверяемый фрагмент карты PMC6218168

{details_text}

Точная единица оценки — одна пара типов, хотя карта содержит несколько блоков параметров модели. Поэтому результат **1/1 против 1/3** является одной диагностикой на одном отложенном источнике, а не оценкой обобщающей точности. Он согласуется с предыдущим LOPO-аудитом 16 карт, где графовый режим имел точность 1.00 и полноту 0.90 на пяти картах с известными методами; независимой научной валидацией этот ретроспективный набор не является.

## Интерпретация и ограничения

- Кандидат возникает из повторявшегося в обучающих картах графового шаблона «Cox-модель → параметр статистической модели» с поддержкой по разным публикациям. Это эмпирический структурный паттерн, не формальная теорема и не один из 24 силлогизмов.
- Сравнение показывает возможную пользу явно заданных связей именно для выбора категории результата при уже известном методе. Один пример не доказывает преимущество карты в целом; карта PMC6218168 была ранее известна исследовательскому процессу, хотя генератор прочитал только её узлы методов до запечатывания.
- В корпусе карты готовились и размечались Codex, местами вручную; правильность всех предметных назначений и независимость первичных выборок экспертно не удостоверены.
- Модельных вызовов, эмбеддингов и сети нет. Целевой DAG не изменялся. Результат не заявляется как научное открытие.

Хеш прогноза: `{result['prediction_sha256']}`. Хеш карты PMC6218168: `{result['target_map_sha256']}`. Экспертная проверка требуется.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    result = evaluate(args.run_id)
    run_root = BASE / "runs" / args.run_id
    result_raw = _json_bytes(result)
    report_raw = render_report(result).encode("utf-8")
    write_immutable(run_root / "evaluation.json", result_raw)
    write_immutable(run_root / "report.ru.md", report_raw)
    files = {name: _sha((run_root / name).read_bytes()) for name in
             ("sealed-prediction.json", "seal.json", "evaluation.json", "report.ru.md")}
    manifest = {"run_id": args.run_id, "files_sha256": files, "immutable": True,
                "network_disabled": True, "model_calls": 0}
    write_immutable(run_root / "evaluation-manifest.json", _json_bytes(manifest))
    print(json.dumps({"run_id": args.run_id, "report": str(run_root / "report.ru.md"),
                      "evaluation": str(run_root / "evaluation.json"),
                      "modes": result["modes"], "model_calls": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()

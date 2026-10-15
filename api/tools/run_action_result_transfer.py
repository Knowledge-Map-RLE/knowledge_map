"""Запускает запечатанный перенос семейств операций на типы результатов."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from hashlib import sha256
from pathlib import Path

from domain.action_result_transfer import (
    MINIMUM_SUPPORT,
    PERMUTATION_SEEDS,
    VERSION,
    extract_article,
    score_predictions,
    seal_permuted_predictions,
    seal_predictions,
)
from domain.article_maps import fingerprint, require
from infrastructure.immutable_files import write_immutable
from tools.run_free_prediction import disable_network

TARGET_SOURCE_SHA256 = "f7df96ff746be4a60a6930ff2c5c25435725d0591dfe1f492259624b2d7c0bc8"


def _json_bytes(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")


def _load_records(manifest: dict) -> tuple[list[dict], list[dict]]:
    entries = manifest.get("sources", [])
    require(bool(entries), "Явный манифест источников обязателен")
    require(len({row["article_id"] for row in entries}) == len(entries),
            "В манифесте повторяются статьи")
    require(TARGET_SOURCE_SHA256 not in {row["source_sha256"] for row in entries},
            "Целевой текст PMC10000452 нельзя включать в обучение")
    records, audit = [], []
    for entry in entries:
        map_path = Path(entry["map_path"])
        map_raw = map_path.read_bytes()
        map_hash = sha256(map_raw).hexdigest()
        require(map_hash == entry["map_sha256"], f"Хеш карты изменён: {entry['article_id']}")
        snapshot = json.loads(map_raw)
        require(snapshot["article_id"] == entry["article_id"],
                f"article_id карты не совпадает: {entry['article_id']}")
        source = snapshot.get("source", {})
        source_text = source.get("text")
        require(isinstance(source_text, str) and source_text,
                f"Полный текст источника отсутствует: {entry['article_id']}")
        source_hash = sha256(source_text.encode("utf-8")).hexdigest()
        require(source_hash == entry["source_sha256"] == source.get("sha256"),
                f"Хеш текста не совпадает: {entry['article_id']}")
        row = extract_article(snapshot, entry.get("support_family"))
        records.append(row)
        audit.append({
            "article_id": entry["article_id"],
            "support_family": row["support_family"],
            "run_id": row["run_id"],
            "map_path": str(map_path),
            "map_sha256": map_hash,
            "source_sha256": source_hash,
            "schema_version": snapshot["graph"]["schema_version"],
            "node_count": len(snapshot["graph"]["nodes"]),
            "visible_edge_count": len(snapshot["graph"].get("edges", [])),
            "transition_count": len(snapshot["graph"].get("transitions", [])),
            "coverage": row["coverage"],
        })
    require(len({row["source_sha256"] for row in audit}) == len(audit),
            "В манифесте повторяются исходные тексты")
    return records, audit


def _percent(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.1f}%"


def _ranking_table(result: dict) -> list[str]:
    rows = [
        "## Ранжирование при равном бюджете",
        "",
        "Для каждой удержанной статьи оба режима ранжируют одинаковый набор: "
        "сочетания её выполненных семейств операций с категориями результатов, "
        "которые встречались в обучающих статьях. Ранг определяется поддержкой "
        "разными публикациями. При ничьей ожидаемое число попаданий считается "
        "дробно по доле правильных пар в группе с одинаковым рангом.",
        "",
        "| Бюджет на статью | Режим | Ожидаемые совпадения | Выдано мест | Точность | Полнота |",
        "|---:|---|---:|---:|---:|---:|",
    ]
    for k in (1, 3, 5, 10):
        for mode, label in (("graph", "Исходные зависимости"),
                            ("same_article_cooccurrence", "Совместное присутствие")):
            values = result["ranked_aggregate"][str(k)][mode]
            rows.append(
                f"| {k} | {label} | {values['expected_hits']:.2f} | "
                f"{values['candidate_slots']} | {_percent(values['precision'])} | "
                f"{_percent(values['recall'])} |"
            )
        control = result["permuted_control"]["ranked_top_k"][str(k)]
        control_precision = (control["expected_hits_mean"] /
                             control["candidate_slots_mean"]
                             if control["candidate_slots_mean"] else None)
        target_count = result["aggregate"]["graph"]["target"]
        control_recall = (control["expected_hits_mean"] / target_count
                          if target_count else None)
        rows.append(
            f"| {k} | Переставленные зависимости, среднее | "
            f"{control['expected_hits_mean']:.2f} | "
            f"{control['candidate_slots_mean']:.1f} | {_percent(control_precision)} | "
            f"{_percent(control_recall)} |"
        )
    rows.append("")
    controls_at_least_graph = "; ".join(
        f"@{k}: {result['permuted_control']['ranked_top_k'][str(k)]['controls_at_least_graph']}"
        f"/{result['permuted_control']['seed_count']}"
        for k in (1, 3, 5, 10)
    )
    rows.append(
        "Перестановок с ожидаемым числом попаданий не меньше графа "
        f"(из {result['permuted_control']['seed_count']}): {controls_at_least_graph}. "
        "Это сравнение чувствительности на ретроспективном корпусе, не p-значение."
    )
    fold_values = [
        (fold["ranked_scores"]["graph"]["3"]["expected_hits"] -
         fold["ranked_scores"]["same_article_cooccurrence"]["3"]["expected_hits"])
        for fold in result["folds"]
    ]
    better = sum(value > 1e-9 for value in fold_values)
    worse = sum(value < -1e-9 for value in fold_values)
    tied = len(fold_values) - better - worse
    rows.append(
        f"При бюджете @3 по отдельным статьям: граф лучше в {better} случаях, "
        f"совпадает в {tied}, хуже в {worse}."
    )
    rows.append("")
    return rows


def _build_report(manifest: dict, result: dict, audit: list[dict], run_id: str) -> str:
    graph = result["aggregate"]["graph"]
    baseline = result["aggregate"]["same_article_cooccurrence"]
    permuted = result["permuted_control"]
    budget_diagnostics = "; ".join(
        f"@{k}: граф {result['ranked_aggregate'][str(k)]['graph']['expected_hits']:.2f}, "
        f"совместное присутствие "
        f"{result['ranked_aggregate'][str(k)]['same_article_cooccurrence']['expected_hits']:.2f}, "
        f"перестановки {permuted['ranked_top_k'][str(k)]['expected_hits_mean']:.2f}"
        for k in (1, 3, 5, 10)
    )
    top_three = result["ranked_aggregate"]["3"]["graph"]["expected_hits"]
    top_three_controls = permuted["ranked_top_k"]["3"]["controls_at_least_graph"]
    action_checked = sum(x["coverage"]["action_statements_checked"] for x in audit)
    action_classified = sum(x["coverage"]["action_statements_classified"] for x in audit)
    state_checked = sum(x["coverage"]["state_predicates_checked"] for x in audit)
    state_classified = sum(
        x["coverage"]["state_predicates_classified_as_reported_outcome"] for x in audit)
    result_category_counts = Counter()
    for source in audit:
        result_category_counts.update(source["coverage"]["reported_outcome_category_counts"])
    rows = [
        "# Перенос типов операций на категории результатов по всей карте",
        "",
        f"**Статус:** исследовательская ретроспективная проверка; новых научных фактов "
        f"не предсказывалось. Идентификатор запуска: `{run_id}`.",
        "",
        "## Что проверялось",
        "",
        f"Из {len(audit)} зафиксированных карт схемы 6 извлекались только явно "
        "выполненные операции и категории связанных с ними результатов. Прогноз "
        "для каждой статьи строился без её выходов и зависимостей; в целевой вход "
        "передавались только семейства выполненных операций. Порог поддержки — "
        f"{manifest['minimum_support']} разные публикации.",
        "",
        "Сравнивались исходные зависимости карты и базовый режим, который видел те же "
        "обучающие статьи, но учитывал лишь совместное присутствие типов операций "
        "и результатов в одной статье. Дополнительно учебные результаты на рёбрах "
        "переставлялись 100 раз при сохранении чисел операций и результатов в каждой статье.",
        "",
        "## Результаты",
        "",
        "| Режим | Кандидатов | Совпадений | Целевых пар | Точность | Полнота |",
        "|---|---:|---:|---:|---:|---:|",
        f"| Исходные зависимости | {graph['predicted']} | {graph['hits']} | {graph['target']} "
        f"| {_percent(graph['precision'])} | {_percent(graph['recall'])} |",
        f"| Совместное присутствие без рёбер | {baseline['predicted']} | {baseline['hits']} | "
        f"{baseline['target']} | {_percent(baseline['precision'])} | {_percent(baseline['recall'])} |",
        f"| Переставленные рёбра, среднее по {permuted['seed_count']} контролям | "
        f"{permuted['predicted_mean']:.1f} | {permuted['hits_mean']:.2f} | "
        f"{graph['target']} | — | — |",
        "",
        f"Перестановок с числом совпадений не меньше исходного графа: "
        f"{permuted['permutations_at_least_graph_hits']} из {permuted['seed_count']}. "
        "Это разведочная проверка чувствительности, не подтверждающее p-значение.",
        "",
        f"Перестановки изменили от {permuted['changed_sources_min']} до "
        f"{permuted['changed_sources_max']} обучающих статей и от "
        f"{permuted['changed_pair_assignments_min']} до "
        f"{permuted['changed_pair_assignments_max']} назначений пар; получено "
        f"{permuted['unique_prediction_sets']} различных наборов прогнозов и "
        f"{permuted['unique_ranked_profiles']} профилей ранжирования. "
        "Поэтому перестановочный контроль имеет ограниченное разнообразие.",
        "",
        *_ranking_table(result),
        "## Интерпретация",
        "",
        "При равном бюджете три категории на статью граф дал "
        f"{top_three:.2f} ожидаемых совпадений; переставленные зависимости "
        "достигали этой оценки в "
        f"{top_three_controls} из {permuted['seed_count']} случаев. "
        f"По другим бюджетам картина меняется ({budget_diagnostics}). "
        "Это ограниченный сигнал того, что структура может улучшать ранжирование "
        "грубых категорий при конкретном бюджете. Перестановки охватили лишь "
        f"две обучающие статьи и {permuted['unique_ranked_profiles']} различных "
        "профилей ранжирования, поэтому результат требует новой заранее "
        "зафиксированной проверки.",
        "",
        "Рёбра могут сужать список категорий по сравнению с простым совместным "
        "присутствием. Но этот результат относится к форме статьи: например, "
        "какой тип результата обычно связан с анализом или измерением. Он не "
        "предсказывает конкретное научное содержание и не подтверждает причинность.",
        "",
        "Таксономия операций составлена после изучения доступных карт, а все статьи "
        "уже были прочитаны в предыдущих опытах. Поэтому оценка постфактум и "
        "исследовательская. Поддержка считается по публикациям, не по независимым "
        "когортам; экспертная проверка карт отсутствует. Преимущество Карты Знаний "
        "для свободного прогноза научных фактов не установлено.",
        "",
        "## Покрытие и воспроизводимость",
        "",
        "| Область | Классифицировано | Проверено | Доля |",
        "|---|---:|---:|---:|",
        f"| Предикаты выполненных действий | {action_classified} | {action_checked} | "
        f"{_percent(action_classified / action_checked if action_checked else None)} |",
        f"| Предикаты состояний, отнесённые к `reported_*` | {state_classified} | "
        f"{state_checked} | "
        f"{_percent(state_classified / state_checked if state_checked else None)} |",
        "",
        "Вторая доля — только охват словаря: знаменатель также содержит определения, "
        "механизмы и другие состояния, которые не являются категориями результатов. "
        "Поэтому её нельзя трактовать как полноту распознавания результатов.",
        "",
        "Число размеченных утверждений по категориям: "
        + "; ".join(f"`{name}` — {count}" for name, count in sorted(result_category_counts.items()))
        + ". Нераспознанные значения сохранены в `input-audit.json` и не "
        "переводятся в общий класс автоматически.",
        "",
        "Сеть и модельные вызовы отключены. Прогнозы записываются до открытия "
        "целевых переходов для подсчёта. Исходные карты и GOLD-файлы не изменялись.",
        "",
    ]
    return "\n".join(rows)


def run(manifest_path: Path, output_path: Path) -> dict:
    disable_network()
    manifest_raw = manifest_path.read_bytes()
    manifest = json.loads(manifest_raw)
    require(manifest.get("minimum_support", MINIMUM_SUPPORT) == MINIMUM_SUPPORT,
            "Версия протокола требует поддержку по двум публикациям")
    records, input_audit = _load_records(manifest)
    code_paths = {
        "domain/action_result_transfer.py":
            Path(__file__).resolve().parents[1] / "domain" / "action_result_transfer.py",
        "tools/run_action_result_transfer.py": Path(__file__).resolve(),
    }
    code_fingerprints = {
        name: sha256(path.read_bytes()).hexdigest()
        for name, path in code_paths.items()
    }
    identity = {
        "version": VERSION,
        "manifest_sha256": sha256(manifest_raw).hexdigest(),
        "code_sha256": fingerprint(code_fingerprints),
        "code_files": code_fingerprints,
        "minimum_support": MINIMUM_SUPPORT,
        "permutation_seeds": list(PERMUTATION_SEEDS),
    }
    run_id = fingerprint(identity)
    run_path = output_path / "runs" / run_id
    run_path.mkdir(parents=True, exist_ok=True)
    write_immutable(run_path / "source-manifest.json", manifest_raw)
    sealed = seal_predictions(records, MINIMUM_SUPPORT)
    write_immutable(run_path / "sealed-prediction.json", _json_bytes(sealed))
    permuted = seal_permuted_predictions(records, MINIMUM_SUPPORT, PERMUTATION_SEEDS)
    write_immutable(run_path / "permuted-predictions.json", _json_bytes(permuted))
    result = score_predictions(records, sealed, permuted)
    result.update(identity)
    write_immutable(run_path / "input-audit.json", _json_bytes({
        "version": VERSION, "sources": input_audit,
        "network_disabled": True, "model_calls": 0,
        "target_source_sha256_excluded": TARGET_SOURCE_SHA256,
    }))
    write_immutable(run_path / "result.json", _json_bytes(result))
    write_immutable(run_path / "report.ru.md", _build_report(manifest, result, input_audit, run_id).encode("utf-8"))
    return {"run_id": run_id, "run_path": str(run_path),
            "sources": result["source_count"], "aggregate": result["aggregate"],
            "permuted_control": result["permuted_control"]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = run(Path(args.manifest), Path(args.output))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

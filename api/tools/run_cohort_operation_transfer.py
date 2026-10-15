"""Проводит отложенный перенос связей метода и результата на картах когорт."""
from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

from domain.article_maps import require
from domain.cohort_operation_transfer import (
    MODEL_PARAMETER_ATTRIBUTES,
    OPERATION_ALIASES,
    OUTPUT_ALIASES,
    VERSION,
    evaluate_lopo,
    extract_map,
)
from infrastructure.immutable_files import write_immutable
from tools.run_free_prediction import disable_network

ROOT = Path(r"D:\Knowledge_Map")
BASE_MANIFEST = ROOT / "eval/whole_map_forecast/research-corpus-extension-v1/cohort-operation-motif-v2/source-manifest.json"
KATZ_MAP = ROOT / "eval/whole_map_forecast/primary-cohort-expansion-codex-v1/runs/cb60299e-851b-546f-902a-1ed898da9561/map.json"
OUTPUT = ROOT / "eval/whole_map_forecast/research-corpus-extension-v1/cohort-operation-transfer-v7"
HELD_OUT_SOURCE_SHA256 = "f7df96ff746be4a60a6930ff2c5c25435725d0591dfe1f492259624b2d7c0bc8"
FAMILY_LABELS_RU = {
    "incidence_estimation": "оценка частоты новых случаев",
    "person_time_calculation": "расчёт человеко-времени",
    "survival_model_fitting": "модель пропорциональных рисков Кокса",
    "reported_association": "сообщаемая связь",
    "reported_frequency": "сообщаемая частота",
    "reported_model_parameter": "параметр статистической модели",
}


def _sha(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def _json_bytes(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")


def _family_label(value: str) -> str:
    return FAMILY_LABELS_RU.get(value, "неизвестная категория")


def _pairs_label(pairs: list[list[str]]) -> str:
    return "; ".join(f"{_family_label(left)} → {_family_label(right)}" for left, right in pairs) or "—"


def prepare() -> tuple[dict, list[dict], dict]:
    base = json.loads(BASE_MANIFEST.read_text(encoding="utf-8"))
    require(len(base.get("sources", [])) == 16, "Ожидался зафиксированный корпус из 16 карт")
    rows = []
    source_files = []
    for entry in base["sources"]:
        path = KATZ_MAP if entry["article_id"] == "katz2012" else Path(entry["path"])
        raw = path.read_bytes()
        snapshot = json.loads(raw)
        require(snapshot["article_id"] == entry["article_id"], "Изменилась идентичность карты")
        require(snapshot["pipeline_id"] == "text_reified" and snapshot["graph_schema_version"] == 6,
                "Требуется карта text_reified схемы 6")
        require(snapshot["source"]["sha256"] == entry["source_sha256"],
                "Исходный текст карты отличается от зафиксированного корпуса")
        require(snapshot["source"]["sha256"] != HELD_OUT_SOURCE_SHA256,
                "Целевая PMC10000452 не должна входить в обучающие карты")
        extract = extract_map(snapshot)
        rows.append(extract)
        source_files.append({
            "article_id": snapshot["article_id"],
            "run_id": snapshot["run_id"],
            "source_sha256": snapshot["source"]["sha256"],
            "map_sha256": _sha(raw),
            "map_path": str(path),
            "family": entry["family"],
            "operator_families": extract["operator_families"],
            "output_families": extract["output_families"],
            "graph_link_count": len(extract["graph_links"]),
        })
    require(len(rows) == 16 and len({row["article_id"] for row in rows}) == 16,
            "Корпус должен содержать 16 уникальных публикаций")
    manifest = {
        "protocol": VERSION,
        "base_manifest_sha256": _sha(BASE_MANIFEST.read_bytes()),
        "target_source_sha256_excluded": HELD_OUT_SOURCE_SHA256,
        "minimum_publication_support": 2,
        "operation_aliases": OPERATION_ALIASES,
        "operation_output_aliases": OUTPUT_ALIASES,
        "model_parameter_attributes": sorted(MODEL_PARAMETER_ATTRIBUTES),
        "implementation_sha256": {
            "domain": _sha((ROOT / "api/domain/cohort_operation_transfer.py").read_bytes()),
            "runner": _sha((ROOT / "api/tools/run_cohort_operation_transfer.py").read_bytes()),
            "operator_routing": _sha((ROOT / "api/domain/operator_frame_routing.py").read_bytes()),
        },
        "sources": source_files,
        "network_disabled": True,
        "external_llm_calls": 0,
        "local_llm_calls": 0,
        "embedding_calls": 0,
        "expert_validated": False,
    }
    result = evaluate_lopo(rows, minimum_support=2)
    return manifest, rows, result


def _ratio(value: float | None) -> str:
    return "н/д" if value is None else f"{value:.3f}"


def build_report(manifest: dict, rows: list[dict], result: dict) -> str:
    aggregate = result["aggregate"]
    graph = aggregate["dependency_edges"]
    baseline = aggregate["same_article_cooccurrence"]
    precision_delta = (graph["precision"] - baseline["precision"]
                       if graph["precision"] is not None and baseline["precision"] is not None else None)
    recall_delta = (graph["recall"] - baseline["recall"]
                    if graph["recall"] is not None and baseline["recall"] is not None else None)
    lines = [
        "# Перенос операций и их результатов между картами когорт",
        "",
        f"Проверено отложенным исключением по одной карте: {len(rows)} карт схемы 6. Минимальная поддержка правила — 2 публикации.",
        "Целевая PMC10000452 исключена по SHA-256. Использовались только сохранённые карты и их переходы; сетевой доступ и вызовы моделей отключены.",
        "",
        "## Сравниваемые режимы",
        "",
        "- **Тип операции** предсказывает, встретится ли типизированная операция в отложенной карте; этот отдельный тест не оценивает пары «операция → результат».",
        "- Для прогноза результата известные узлы методов отложенной карты задаются как контекст. Выходные знания и связи к ним используются только при оценке.",
        "- **Совместная встречаемость без рёбер** связывает известный тип операции с каждым типом результата, обнаруженным в той же обучающей статье.",
        "- **Переходы графа** учат связь только по прямым переходам от узла операции к знанию результата. Неоднозначные группы с несколькими узлами-операциями исключаются.",
        "",
        "Результаты приведены по точности и полноте; для пар операции–результат оцениваются уникальные типизированные пары, а поддержку считают по публикациям.",
        "",
        "## Прогноз наличия операции на всех 16 отложенных картах",
        "",
        "| Режим | Совпавшие типы | Предсказания | Типы в целевых картах | Точность | Полнота |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    labels = {
        "operator_family_only": "Тип операции",
        "same_article_cooccurrence": "Совместная встречаемость без рёбер",
        "dependency_edges": "Переходы графа",
    }
    item = aggregate["operator_family_only"]
    lines.append(f"| {labels['operator_family_only']} | {item['hits']} | {item['predicted']} | {item['target']} | {_ratio(item['precision'])} | {_ratio(item['recall'])} |")
    pair_folds = sum(fold["scored_for_operator_conditioned_forecast"] for fold in result["folds"])
    lines.extend([
        "",
        f"## Прогноз категории результата при известной операции: {pair_folds} отложенных карт с подходящими узлами методов",
        "",
        "| Режим | Совпавшие пары | Предсказания | Пары в целевых картах | Точность | Полнота |",
        "|---|---:|---:|---:|---:|---:|",
    ])
    for mode in ("same_article_cooccurrence", "dependency_edges"):
        item = aggregate[mode]
        lines.append(f"| {labels[mode]} | {item['hits']} | {item['predicted']} | {item['target']} | {_ratio(item['precision'])} | {_ratio(item['recall'])} |")
    lines.extend([
        "",
        f"Для этих пар разница графового режима относительно совместной встречаемости без рёбер: точность **{_ratio(precision_delta)}**, полнота **{_ratio(recall_delta)}**.",
        "",
        "## Операции, реально встретившиеся в корпусе",
        "",
        "| Публикация | Операции | Типы выходных знаний | Прямые связи в карте |",
        "|---|---|---|---:|",
    ])
    for row in manifest["sources"]:
        operations = ", ".join(_family_label(item) for item in row["operator_families"]) or "—"
        outputs = ", ".join(_family_label(item) for item in row["output_families"]) or "—"
        lines.append(f"| {row['article_id']} | {operations} | {outputs} | {row['graph_link_count']} |")
    eligible_folds = [fold for fold in result["folds"] if fold["scored_for_operator_conditioned_forecast"]]
    if eligible_folds:
        lines.extend([
            "",
            "## Ошибки по отложенным картам",
            "",
            "| Статья | Известные методические узлы | Истинные пары | Без рёбер: совпадения/кандидаты | Граф: совпадения/кандидаты | Пропущено графом |",
            "|---|---|---|---:|---:|---|",
        ])
        for fold in eligible_folds:
            operations = ", ".join(_family_label(item) for item in fold["target_operator_families"])
            no_edges = fold["scores"]["same_article_cooccurrence"]
            graph_score = fold["scores"]["dependency_edges"]
            lines.append(
                f"| {fold['target_article_id']} | {operations} | {_pairs_label(fold['target_links'])} | "
                f"{no_edges['hits']}/{no_edges['predicted_count']} | {graph_score['hits']}/{graph_score['predicted_count']} | "
                f"{_pairs_label(graph_score['missed_pairs'])} |"
            )
    lines.extend([
        "",
        "## Интерпретация и границы",
        "",
        "Этот тест проверяет перенос связи «описанная аналитическая операция → категория сообщаемого результата», а не предсказывает новый научный факт или численную оценку. Предполагается, что методические узлы отложенной статьи доступны до её результатов; это условие проверяется только по картам и не подтверждено слепым экспериментом. Положительная разница графового режима показала бы пользу рёбер для восстановления авторской структуры в этих картах; она сама по себе не доказывает преимущество в научном прогнозе.",
        "",
        "Это ретроспективное LOPO по ранее подготовленным и частично вручную формализованным картам. Публикации принадлежат тематически близкой области; независимость выборок и экспертная корректность разметки не подтверждены. Карты и GOLD-источники не изменялись.",
        "",
        "Алиасы операций и выходных предикатов сохранены в манифесте. Утверждения с атрибутами hazard ratio, odds ratio, risk ratio или коэффициента модели относятся к численным параметрам модели, даже если исходный предикат называет их связью. Исходные предикаты не меняются; неизвестные типы результата не угадываются.",
        "",
        "Вызовов внешних/локальных LLM, переводчика и эмбеддингов — **0**. Экспертная проверка не проводилась.",
    ])
    return "\n".join(lines) + "\n"


def main() -> None:
    disable_network()
    manifest, rows, result = prepare()
    manifest_bytes = _json_bytes(manifest)
    result_bytes = _json_bytes(result)
    run_id = _sha(manifest_bytes + result_bytes)[:32]
    run_root = OUTPUT / "runs" / run_id
    write_immutable(OUTPUT / "source-manifest.json", manifest_bytes)
    write_immutable(run_root / "result.json", result_bytes)
    write_immutable(run_root / "report.ru.md", build_report(manifest, rows, result).encode("utf-8"))
    run = {
        "run_id": run_id,
        "protocol": VERSION,
        "source_manifest_sha256": _sha(manifest_bytes),
        "result_sha256": _sha(result_bytes),
        "map_count": len(rows),
        "minimum_publication_support": 2,
        "operator_conditioned_result_forecast_maps": sum(
            bool(row["operator_families"]) for row in rows
        ),
        "network_disabled": True,
        "external_llm_calls": 0,
        "local_llm_calls": 0,
        "embedding_calls": 0,
        "scientific_fact_forecast": False,
        "expert_validated": False,
    }
    write_immutable(run_root / "run.json", _json_bytes(run))
    print(json.dumps({"run_id": run_id, "report": str(run_root / "report.ru.md"),
                      "aggregate": result["aggregate"], "model_calls": 0,
                      "network_disabled": True}, ensure_ascii=False))


if __name__ == "__main__":
    main()

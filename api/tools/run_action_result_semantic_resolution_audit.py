"""Проверяет, на каком уровне семантической точности межстатейные шаблоны исчезают."""
from __future__ import annotations

import argparse
import json
import logging
from hashlib import sha256
from pathlib import Path

from domain.action_result_semantic_resolution import (
    LEVELS, MINIMUM_SUPPORT, VERSION, extract_article, score_forecasts, seal_forecasts,
)
from domain.article_maps import fingerprint, require
from infrastructure.immutable_files import write_immutable
from tools.run_action_result_free_citation_audit import (
    DEFAULT_MANIFEST, DEFAULT_OUTPUT, _citation_exclusions, _source_snapshots,
)
from tools.run_action_result_transfer import TARGET_SOURCE_SHA256, _load_records
from tools.run_free_prediction import disable_network

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "eval/whole_map_forecast/action-result-semantic-resolution-v1"


def _json_bytes(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")


def _report(result: dict) -> str:
    labels = {
        0: "Семейство результата",
        1: "Добавлен точный предикат результата",
        2: "Добавлены роли, отрицание, квантор и модальность",
        3: "Добавлены вид знания и логика блока",
        4: "Добавлены поля атрибутов с единицами и признаки контекста",
    }
    lines = [
        "# На каком уровне семантики перестаёт переноситься шаблон результата",
        "",
        "**Это диагностика переносимости шаблонов, а не прогноз численных научных выводов.** "
        "Все пять уровней строятся на одних и тех же картах; целевые операции, результаты "
        "и связи используются только после фиксации кандидатов.",
        "",
        f"Карт: {result['source_count']}; найденных пар «цель–цитатор»: "
        f"{result['citation_exclusion_count']}; минимальная поддержка: "
        f"{result['minimum_support']} публикации.",
        "",
        "В каждом фолде исключались сама цель и все найденные прямые цитаторы. "
        "Связанный режим использовал только прямые переходы от одного распознанного "
        "выполненного действия к знанию-результату. Контроль без зависимостей видел "
        "те же статьи и те же шаблоны, но сочетал их по совместному присутствию. "
        "Численные значения не переносились.",
        "",
        "## Результаты",
        "",
        "| Уровень шаблона | Режим | Кандидатов | Совпадений | Целевых шаблонов | Точность | Полнота |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    names = {"graph": "Связи карты", "without_dependencies": "Без зависимостей"}
    for level in LEVELS:
        for mode in ("graph", "without_dependencies"):
            row = result["scores"]["aggregate"][mode][level]
            precision = "—" if row["precision"] is None else f"{row['precision']:.3f}"
            recall = "—" if row["recall"] is None else f"{row['recall']:.3f}"
            lines.append(
                f"| {labels[level]} | {names[mode]} | {row['predicted']} | {row['hits']} | "
                f"{row['target']} | {precision} | {recall} |"
            )
    lines.extend(["", "## Где исчезает повторяемость", ""])
    base = result["scores"]["aggregate"]
    lines.append(
        f"На уровне семейств исходный граф воспроизводит предыдущий аудит: "
        f"{base['graph'][0]['hits']}/{base['graph'][0]['predicted']} совпадений; "
        f"совместное присутствие без рёбер — {base['without_dependencies'][0]['hits']}/"
        f"{base['without_dependencies'][0]['predicted']}."
    )
    lines.append(
        f"При добавлении точного предиката остаётся "
        f"{base['graph'][1]['hits']} совпадение(й) из {base['graph'][1]['predicted']} "
        f"графовых кандидатов; контроль без рёбер даёт "
        f"{base['without_dependencies'][1]['hits']} из "
        f"{base['without_dependencies'][1]['predicted']}."
    )
    lines.append(
        f"При добавлении ролей и логических ограничений графовый режим с порогом "
        f"поддержки {result['minimum_support']} не формирует кандидатов. Это значит, "
        "что в этих 19 картах не найден точный повтор такого шаблона как минимум "
        "в двух публикациях; это не доказывает невозможность переноса после "
        "обоснованного сопоставления ролей и контекстов."
    )
    matched = []
    for fold in result["scores"]["folds"]:
        match_rows = fold["levels"][1]["graph"]["matched"]
        if match_rows:
            matched.append(fold["target_article_id"])
    lines.append(
        "Единственное точное совпадение на уровне предиката относится к отложенной "
        f"статье `{', '.join(sorted(matched))}`. Оно показывает повтор типа утверждения, "
        "но не совпадение его участников, значений или области применимости."
        if matched else "На уровне точного предиката совпадений нет."
    )
    lines.extend([
        "",
        "## Вывод и следующий шаг",
        "",
        "Текущая сильная сторона связей проявляется только при грубой классификации "
        "типа результата. Для содержательного прогноза нужно согласовать межстатейные "
        "понятия участников и роли, затем проверять полные предикатные шаблоны, "
        "единицы, отрицание, модальность, время и предметную область. Сопоставление "
        "должно опираться на явные словари и источники, а не снимать различия ради "
        "получения повторов. Следующий тест также требует большего числа независимых "
        "первичных статей; одни дополнительные карты обзоров могут лишь повторять "
        "цитируемые данные.",
        "",
        "Эта проверка не применяла 24 категорических силлогизма: она оценивает "
        "перенос шаблонов «операция → результат». Логические выводы остаются отдельным "
        "семейством методов с собственными условиями лицензирования.",
        "",
        "Проверка ретроспективная; экспертная научная валидация не проводилась. "
        "Модельных вызовов — 0; сеть отключена.",
        "",
    ])
    return "\n".join(lines)


def run(manifest_path: Path = DEFAULT_MANIFEST,
        output_path: Path = OUTPUT) -> Path:
    disable_network()
    manifest_raw = manifest_path.read_bytes()
    manifest = json.loads(manifest_raw)
    metadata = manifest.get("metadata", {})
    require(metadata.get("target_article_id_excluded") == "PMC10000452",
            "Манифест должен исключать целевую PMC10000452")
    require(metadata.get("target_source_sha256_excluded") == TARGET_SOURCE_SHA256,
            "Манифест цели не совпадает с утверждённым SHA-256")
    _, input_audit = _load_records(manifest)
    snapshots = _source_snapshots(manifest)
    support_families = {row["article_id"]: row.get("support_family", row["article_id"])
                        for row in manifest["sources"]}
    records = [extract_article(snapshots[article_id], support_families[article_id])
               for article_id in sorted(snapshots)]
    require({row["article_id"] for row in records} == set(support_families),
            "Состав карт не совпадает с манифестом")
    exclusions, citation_matches = _citation_exclusions(records, snapshots)
    sealed = seal_forecasts(records, exclusions, MINIMUM_SUPPORT)
    scores = score_forecasts(records, sealed)

    implementation_paths = [
        Path(__file__).resolve(),
        Path(__file__).resolve().parents[1] / "domain" / "action_result_semantic_resolution.py",
        Path(__file__).resolve().parents[1] / "domain" / "action_result_transfer.py",
        Path(__file__).resolve().parents[1] / "domain" / "operator_frame_routing.py",
        Path(__file__).resolve().parent / "run_action_result_free_citation_audit.py",
        Path(__file__).resolve().parent / "run_action_result_transfer.py",
    ]
    implementation = {
        str(path.relative_to(ROOT)): sha256(path.read_bytes()).hexdigest()
        for path in implementation_paths
    }
    identity = {
        "version": VERSION,
        "source_manifest_sha256": sha256(manifest_raw).hexdigest(),
        "implementation_sha256": implementation,
        "minimum_support": MINIMUM_SUPPORT,
        "levels": LEVELS,
        "citation_matcher_version": "exact-doi-title-pmcid-author-year-v2",
    }
    run_id = fingerprint(identity)
    result = {
        "run_id": run_id,
        **identity,
        "source_count": len(records),
        "source_audit": input_audit,
        "citation_exclusion_count": len(citation_matches),
        "citation_matches": citation_matches,
        "citation_exclusions": exclusions,
        "sealed_forecasts": sealed,
        "scores": scores,
        "target_source_sha256_excluded": TARGET_SOURCE_SHA256,
        "target_operations_used": False,
        "target_outcomes_or_dependencies_used": False,
        "network_disabled": True,
        "model_calls": 0,
        "expert_validated": False,
    }
    payloads = {
        "data.json": _json_bytes(result),
        "sealed-prediction.json": _json_bytes(sealed),
        "report.ru.md": _report(result).encode("utf-8"),
    }
    verification = {
        "run_id": run_id,
        "files_sha256": {name: sha256(raw).hexdigest() for name, raw in payloads.items()},
        "source_count": len(records),
        "citation_exclusion_count": len(citation_matches),
        "target_operations_used": False,
        "target_outcomes_or_dependencies_used": False,
        "network_disabled": True,
        "model_calls": 0,
        "expert_validated": False,
    }
    payloads["verification.json"] = _json_bytes(verification)
    run_path = output_path / "runs" / run_id
    run_path.mkdir(parents=True, exist_ok=True)
    for name, content in payloads.items():
        write_immutable(run_path / name, content)
    logging.info("action_result_semantic_resolution_complete run=%s sources=%d citations=%d",
                 run_id, len(records), len(citation_matches))
    return run_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    print(run(args.manifest, args.output))


if __name__ == "__main__":
    main()

"""Сравнивает перенос категории результата по прямым переходам на 19 картах."""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from hashlib import sha256
from pathlib import Path

from domain.article_maps import fingerprint, require
from domain.cohort_operation_result_transfer import extract_map as extract_result_map
from domain.cohort_operation_transfer import (
    OPERATION_ALIASES,
    OUTPUT_ALIASES,
    extract_map,
    forecast_for_known_operations,
    score,
)
from infrastructure.immutable_files import write_immutable
from tools.run_free_prediction import disable_network


ROOT = Path(r"D:\Knowledge_Map")
BASE_MANIFEST = ROOT / (
    "eval/whole_map_forecast/semantic-parts-v1/"
    "full-corpus-19-prepared-v1/source-manifest.json"
)
OUTPUT = ROOT / (
    "eval/whole_map_forecast/cohort_operation_prediction/"
    "full19-result-usage-diagnostic-v1"
)
TARGET_SOURCE_SHA256 = "f7df96ff746be4a60a6930ff2c5c25435725d0591dfe1f492259624b2d7c0bc8"
VERSION = "full19-cohort-result-usage-diagnostic-1"
MINIMUM_SUPPORT = 2
MODES = (
    "same_article_cooccurrence",
    "dependency_edges_all_usage",
    "dependency_edges_result_usage",
)


def _sha(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def _json_bytes(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")


def _read_sources() -> tuple[dict, list[dict], dict[str, dict]]:
    manifest_raw = BASE_MANIFEST.read_bytes()
    manifest = json.loads(manifest_raw.decode("utf-8"))
    require(len(manifest.get("sources", [])) == 19, "Ожидались ровно 19 источников")
    require(manifest["metadata"].get("target_article_id_excluded") == "PMC10000452",
            "В манифесте должен быть указан исключённый целевой источник")
    sources, extracted = [], {}
    seen = set()
    for entry in manifest["sources"]:
        path = Path(entry["path"])
        raw = path.read_bytes()
        require(_sha(raw) == entry["file_sha256"], "Изменилась карта из манифеста")
        snapshot = json.loads(raw.decode("utf-8"))
        article_id = snapshot["article_id"]
        require(article_id == entry["reference"]["article_id"], "Не совпал id карты")
        require(article_id not in seen, "Повторилась статья в манифесте")
        require(snapshot["source"]["sha256"] == entry["source_sha256"], "Не совпал хеш текста")
        require(fingerprint(snapshot["graph"]) == entry["graph_sha256"], "Изменился граф из манифеста")
        require(snapshot["source"]["sha256"] != TARGET_SOURCE_SHA256,
                "Целевой текст PMC10000452 обнаружен в обучении")
        seen.add(article_id)
        extracted[article_id] = extract_map(snapshot)
        sources.append({
            "article_id": article_id,
            "family": entry["family"],
            "run_id": snapshot["run_id"],
            "source_sha256": snapshot["source"]["sha256"],
            "map_sha256": _sha(raw),
            "graph_sha256": entry["graph_sha256"],
            "map_path": str(path),
        })
    return manifest, sources, extracted


_SNAPSHOTS: dict[str, dict] = {}


def _lopo(rows_by_source: dict[str, dict]) -> list[dict]:
    results = []
    for target_id in sorted(rows_by_source):
        target = rows_by_source[target_id]
        training = {key: value for key, value in rows_by_source.items() if key != target_id}
        forecasts = forecast_for_known_operations(
            training, set(target["operator_families"]), MINIMUM_SUPPORT
        )
        truth = {
            tuple(pair)
            for pair in extract_result_map(_SNAPSHOTS[target_id])["graph_links"]
        }
        candidate_sets = {
            "same_article_cooccurrence": {
                tuple(pair) for pair in forecasts["same_article_cooccurrence"]
            },
            "dependency_edges_all_usage": {
                tuple(pair) for pair in forecasts["dependency_edges"]
            },
        }
        # Повторяем прогноз на обучении, где оставлены только result-переходы.
        result_training = {
            key: extract_result_map(_SNAPSHOTS[key]) for key in training
        }
        result_forecast = forecast_for_known_operations(
            result_training, set(target["operator_families"]), MINIMUM_SUPPORT
        )
        candidate_sets["dependency_edges_result_usage"] = {
            tuple(pair) for pair in result_forecast["dependency_edges"]
        }
        scored = bool(truth)
        results.append({
            "target_article_id": target_id,
            "scored": scored,
            "target_result_pairs": [list(pair) for pair in sorted(truth)],
            "modes": {
                mode: score(candidates, truth) if scored else {
                    "predicted_count": len(candidates), "target_count": 0, "hits": 0,
                    "precision": None, "recall": None, "matched_pairs": [],
                    "missed_pairs": [], "extra_pairs": [list(p) for p in sorted(candidates)]
                }
                for mode, candidates in candidate_sets.items()
            },
            "target_operations": sorted(target["operator_families"]),
            "training_source_ids": sorted(training),
        })
    return results


def _aggregate(folds: list[dict]) -> dict:
    aggregate = {
        mode: {"predicted": 0, "target": 0, "hits": 0}
        for mode in MODES
    }
    scored_folds = [fold for fold in folds if fold["scored"]]
    for fold in scored_folds:
        for mode in MODES:
            row = fold["modes"][mode]
            aggregate[mode]["predicted"] += row["predicted_count"]
            aggregate[mode]["target"] += row["target_count"]
            aggregate[mode]["hits"] += row["hits"]
    for row in aggregate.values():
        row["precision"] = row["hits"] / row["predicted"] if row["predicted"] else None
        row["recall"] = row["hits"] / row["target"] if row["target"] else None
    return {"eligible_target_count": len(scored_folds), "fold_count": len(folds), "modes": aggregate}


def _render_ru(result: dict) -> str:
    labels = {
        "same_article_cooccurrence": "Совместная встречаемость без рёбер",
        "dependency_edges_all_usage": "Все прямые связи",
        "dependency_edges_result_usage": "Только связи с меткой `result`",
    }
    lines = [
        "# Проверка перехода «операция → категория результата» на 19 картах",
        "",
        "**Это диагностический прогноз категории блока, а не прогноз нового научного факта.**",
        "Целевая PMC10000452 исключена по хешу исходного текста. Каждая карта по очереди удерживалась; для прогноза использовались только остальные карты и известные в удержанной карте операции.",
        "",
        f"Корпус: {len(result['sources'])} карт; целей с явными переходами `usage=result`, пригодных для оценки: {result['aggregate']['eligible_target_count']} из {result['aggregate']['fold_count']}. Минимальная поддержка связи — {MINIMUM_SUPPORT} публикации.",
        "",
        "## Итог LOPO",
        "",
        "| Режим | Совпадения / прогнозы | Истинные пары | Точность | Полнота |",
        "|---|---:|---:|---:|---:|",
    ]
    for mode in MODES:
        value = result["aggregate"]["modes"][mode]
        precision = "—" if value["precision"] is None else f"{value['precision']:.3f}"
        recall = "—" if value["recall"] is None else f"{value['recall']:.3f}"
        lines.append(
            f"| {labels[mode]} | {value['hits']}/{value['predicted']} | {value['target']} | {precision} | {recall} |"
        )
    lines.extend([
        "",
        "## Цели",
        "",
        "| Целевая карта | `usage=result` пары | Без рёбер | Все связи | Только `result` |",
        "|---|---|---:|---:|---:|",
    ])
    for fold in result["folds"]:
        targets = "; ".join(
            f"{a} → {b}" for a, b in fold["target_result_pairs"]
        ) or "—"
        cells = []
        for mode in MODES:
            row = fold["modes"][mode]
            cells.append(f"{row['hits']}/{row['predicted_count']}" if fold["scored"] else "не оценено")
        lines.append(f"| {fold['target_article_id']} | {targets} | {cells[0]} | {cells[1]} | {cells[2]} |")
    lines.extend([
        "",
        "## Интерпретация",
        "",
        "Результат следует читать только по явно размеченным целевым `result`-переходам. Цели без такой разметки считаются неоценёнными, а не отрицательными примерами. Даже превосходство прямых связей над безрёберным режимом покажет пока лишь перенос категории результата при известной операции; оно не подтвердит предсказание содержания, причинности или нового статистического эффекта.",
        "",
        "Метки `usage` описывают разные роли перехода и ранее расходились для одинаковых пар «операция → категория»: `method`, `data`, `premise` и `result`. Поэтому сравнение широкого режима со строгим нужно интерпретировать вместе с этой неоднородностью. Поддержка считается по публикациям, независимость участников не удостоверена.",
        "",
        "Прогноз LOPO является ретроспективной диагностикой на уже собранных картах, не слепым проспективным испытанием. Модельных и сетевых вызовов — 0; исходные карты не изменялись; экспертная научная оценка не проводилась.",
        "",
    ])
    return "\n".join(lines)


def run() -> Path:
    disable_network()
    manifest, source_rows, extracted = _read_sources()
    global _SNAPSHOTS
    _SNAPSHOTS = {}
    for row in source_rows:
        _SNAPSHOTS[row["article_id"]] = json.loads(Path(row["map_path"]).read_text(encoding="utf-8"))
    folds = _lopo(extracted)
    aggregate = _aggregate(folds)
    usage_support: dict[str, set[str]] = defaultdict(set)
    usage_transitions: dict[str, int] = defaultdict(int)
    for source_id, snapshot in _SNAPSHOTS.items():
        strict = extract_result_map(snapshot)
        for pair in strict["graph_links"]:
            key = "|".join(pair)
            for _ in strict["graph_evidence"][key]:
                usage_support[key].add(source_id)
                usage_transitions[key] += 1
    implementation_paths = [
        ROOT / "api/domain/cohort_operation_transfer.py",
        ROOT / "api/domain/cohort_operation_result_transfer.py",
        ROOT / "api/domain/operator_frame_routing.py",
        ROOT / "api/domain/operator_pattern_forecast.py",
        ROOT / "api/tools/run_full19_cohort_result_usage_diagnostic.py",
    ]
    implementation = {str(path.relative_to(ROOT)): _sha(path.read_bytes()) for path in implementation_paths}
    result = {
        "version": VERSION,
        "manifest_sha256": _sha(BASE_MANIFEST.read_bytes()),
        "source_count": len(source_rows),
        "sources": source_rows,
        "minimum_publication_support": MINIMUM_SUPPORT,
        "aggregate": aggregate,
        "folds": folds,
        "strict_result_link_support": [
            {"pair": key, "publication_count": len(article_ids),
             "transition_count": usage_transitions[key], "article_ids": sorted(article_ids)}
            for key, article_ids in sorted(usage_support.items())
        ],
        "operation_aliases": OPERATION_ALIASES,
        "output_aliases": OUTPUT_ALIASES,
        "implementation_sha256": implementation,
        "target_source_sha256_excluded": TARGET_SOURCE_SHA256,
        "network_disabled": True,
        "external_llm_calls": 0,
        "local_llm_calls": 0,
        "embedding_calls": 0,
        "expert_validated": False,
    }
    run_id = fingerprint({"version": VERSION, "manifest_sha256": result["manifest_sha256"],
                          "implementation_sha256": implementation, "minimum_support": MINIMUM_SUPPORT})
    result["run_id"] = run_id
    files = {
        "data.json": _json_bytes(result),
        "report.ru.md": _render_ru(result).encode("utf-8"),
    }
    verification = {
        "run_id": run_id,
        "files_sha256": {name: _sha(raw) for name, raw in files.items()},
        "input_map_count": len(source_rows),
        "target_source_excluded_by_sha256": True,
        "network_disabled": True,
        "model_calls": 0,
        "expert_validated": False,
    }
    files["verification.json"] = _json_bytes(verification)
    output = OUTPUT / "runs" / run_id
    output.mkdir(parents=True, exist_ok=True)
    for name, raw in files.items():
        write_immutable(output / name, raw)
    logging.info("full19_result_usage_complete run=%s eligible=%d", run_id,
                 aggregate["eligible_target_count"])
    return output


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    print(run())


if __name__ == "__main__":
    main()

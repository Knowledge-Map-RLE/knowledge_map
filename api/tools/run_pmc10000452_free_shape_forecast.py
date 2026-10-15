"""Запечатывает свободный структурный прогноз перед чтением графа целевой статьи."""
from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path

from domain.article_maps import fingerprint, require
from domain.development_prediction import validate_visible_dag
from tools.run_full19_transition_pattern_forecast import (
    DEFAULT_MANIFEST,
    MINIMUM_PUBLICATION_SUPPORT,
    MAXIMUM_ARITY,
    TARGET_SOURCE_SHA256,
    _article_citation_keys,
    _citation_matches,
    _cooccurrence_details,
    _graph_predictions,
    _score,
    _shape,
    _shape_id,
    _top_k_score,
    _type_ru,
    _usage_predictions,
)


ROOT = Path(r"D:\Knowledge_Map")
TARGET_DIR = ROOT / (
    "eval/article_comparisons/pmc10000452-codex-v1/"
    "4bfddde7bbae6e8e60b84dcf9aa86678f8cca985ca153b89bd24514ee933ea83/"
    "review/maps/pmc10000452"
)
TARGET_SOURCE_PATH = TARGET_DIR / "source.json"
TARGET_MAP_PATH = TARGET_DIR / "map.json"
TARGET_ARTICLE_ID = "pilot-pmc10000452-pmc10000452-f7df96ff746be4a6"
TARGET_DOI = "10.3390/healthcare11050703"
TARGET_PMCID = "pmc10000452"
TARGET_TITLE = (
    "Cretan Aging Cohort-Phase III: Methodology and Descriptive Characteristics "
    "of a Long-Term Longitudinal Study on Predictors of Cognitive Decline in "
    "Non-Demented Elderly from Crete, Greece"
)
VERSION = "pmc10000452-free-transition-shape-sealed-v2"


def _sha(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def _json_bytes(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")


def _external_target_markers() -> dict:
    return {
        "article_id": TARGET_ARTICLE_ID,
        "citation_keys": {
            "doi": TARGET_DOI,
            "own_pmcid": TARGET_PMCID,
            "title": TARGET_TITLE,
            "title_key": " ".join(
                TARGET_TITLE.casefold()
                .replace(":", " ")
                .replace("-", " ")
                .replace(",", " ")
                .split()
            ),
        },
    }


def _build_forecast(
    manifest_path: Path,
    excluded_article_ids: tuple[str, ...] = (),
) -> dict:
    from tools.run_full19_transition_pattern_forecast import _load_articles

    articles, manifest_meta = _load_articles(manifest_path)
    require(TARGET_ARTICLE_ID not in articles, "Целевая статья присутствует в обучающих картах")
    require(
        all(article["source_sha256"] != TARGET_SOURCE_SHA256 for article in articles.values()),
        "Целевой текст найден среди обучающих карт",
    )
    explicit_exclusion_ids = set(excluded_article_ids)
    require(explicit_exclusion_ids <= set(articles), "Явно исключённой статьи нет в манифесте")
    target_markers = _external_target_markers()
    direct_citation_exclusions = []
    explicit_exclusions = []
    training = {}
    for article_id, article in articles.items():
        if article_id in explicit_exclusion_ids:
            explicit_exclusions.append({
                "citing_article_id": article_id,
                "source_sha256": article["source_sha256"],
                "reason": "карта отнесена к той же исследовательской когорте",
            })
            continue
        matches = _citation_matches(target_markers, article)
        if matches:
            direct_citation_exclusions.append({
                "citing_article_id": article_id,
                "source_sha256": article["source_sha256"],
                "evidence": matches,
            })
        else:
            training[article_id] = article

    edge_ids, edge_support = _graph_predictions(training)
    no_edge_ids, no_edge_support, no_edge_catalog = _cooccurrence_details(training)
    usage_ids, usage_support = _usage_predictions(training)
    edge_catalog = {
        _shape_id(shape): shape
        for article in training.values()
        for shape in article["shapes"]
    }
    usage_catalog = {
        fingerprint(signature): signature
        for article in training.values()
        for signature in article["usage_shapes"]
    }

    def candidates(ids: set[str], support: dict, catalog: dict) -> list[dict]:
        return [
            {
                "signature_id": key,
                "shape": catalog[key],
                "article_support": sorted(support[key]),
                "support_count": len(support[key]),
            }
            for key in sorted(ids, key=lambda item: (-len(support[item]), item))
        ]

    return {
        "version": VERSION,
        "target": {
            "article_id": TARGET_ARTICLE_ID,
            "source_sha256": TARGET_SOURCE_SHA256,
            "doi_for_citation_exclusion_only": TARGET_DOI,
            "pmcid_for_citation_exclusion_only": TARGET_PMCID,
        },
        "training_manifest": manifest_meta,
        "training_article_count": len(training),
        "training_article_ids": sorted(training),
        "explicit_exclusion_ids": sorted(explicit_exclusion_ids),
        "training_source_sha256": {
            article_id: training[article_id]["source_sha256"]
            for article_id in sorted(training)
        },
        "training_map_sha256": {
            article_id: training[article_id]["raw_sha256"]
            for article_id in sorted(training)
        },
        "training_graph_sha256": {
            article_id: training[article_id]["graph_sha256"]
            for article_id in sorted(training)
        },
        "direct_citation_exclusions": direct_citation_exclusions,
        "explicit_source_exclusions": explicit_exclusions,
        "minimum_article_support": MINIMUM_PUBLICATION_SUPPORT,
        "maximum_transition_arity": MAXIMUM_ARITY,
        "model_calls": 0,
        "network_calls": 0,
        "target_graph_read_before_seal": False,
        "forecast_inputs": [
            "только 19 карт и source_sha256 из зафиксированного обучающего манифеста",
            "типизированные группы переходов этих обучающих графов",
            "совместная встречаемость типов блоков внутри обучающих статей",
        ],
        "candidate_modes": {
            "dependency_graph": candidates(edge_ids, edge_support, edge_catalog),
            "without_edges": candidates(no_edge_ids, no_edge_support, no_edge_catalog),
            "dependency_graph_with_usage": candidates(usage_ids, usage_support, usage_catalog),
        },
    }


def _target_truth(target_map_path: Path, target_source_path: Path) -> tuple[dict, dict]:
    source_raw = target_source_path.read_bytes()
    source = json.loads(source_raw.decode("utf-8"))
    require(source["article_id"] == TARGET_ARTICLE_ID, "Идентификатор source.json не совпал")
    require(source["sha256"] == TARGET_SOURCE_SHA256, "SHA-256 исходного текста цели не совпал")
    require(_sha(source["text"].encode("utf-8")) == TARGET_SOURCE_SHA256, "Текст цели изменён")
    raw_map = target_map_path.read_bytes()
    map_manifest = json.loads((target_map_path.parent / "manifest.json").read_text(encoding="utf-8"))
    require(map_manifest["article_id"] == TARGET_ARTICLE_ID, "Идентификатор манифеста карты не совпал")
    require(map_manifest["source_sha256"] == TARGET_SOURCE_SHA256, "Манифест указывает другой исходный текст")
    require(_sha(source_raw) == map_manifest["files"]["source.json"], "Хеш source.json не совпал с манифестом")
    require(_sha(raw_map) == map_manifest["files"]["map.json"], "Хеш целевой карты не совпал с её манифестом")
    article = json.loads(raw_map.decode("utf-8"))
    require(article["article_id"] == TARGET_ARTICLE_ID, "Идентификатор целевой карты не совпал")
    require(article["graph_schema_version"] == 6, "Ожидалась целевая карта схемы 6")
    require(article["source"]["sha256"] == TARGET_SOURCE_SHA256, "Карта построена не из подтверждённого текста")
    validate_visible_dag(article["graph"])
    source_keys = _article_citation_keys(
        {"source": {"text": source["text"]}},
        source["article_id"],
    )
    require(source_keys["doi"] == TARGET_DOI, "DOI целевого текста не совпал")
    return article, {
        "source_sha256": TARGET_SOURCE_SHA256,
        "source_file_sha256": _sha(source_raw),
        "map_file_sha256": _sha(raw_map),
        "graph_sha256": fingerprint(article["graph"]),
        "graph_schema_version": article["graph_schema_version"],
        "run_id": article["run_id"],
        "validated_dag": True,
    }


def _evaluate(forecast: dict, target_article: dict, target_meta: dict) -> dict:
    graph = target_article["graph"]
    nodes = {node["id"]: node["knowledge_id"] for node in graph["nodes"]}
    knowledge = {item["knowledge_id"]: item for item in graph["knowledge"]}
    structural_truth = []
    usage_truth = []
    for transition in graph["transitions"]:
        source_types = [
            f"{knowledge[nodes[node_id]]['kind']}/"
            f"{knowledge[nodes[node_id]]['knowledge_kind']}"
            for node_id in transition["sources"]
        ]
        if len(source_types) > MAXIMUM_ARITY:
            continue
        target_type = (
            f"{knowledge[nodes[transition['target']]]['kind']}/"
            f"{knowledge[nodes[transition['target']]]['knowledge_kind']}"
        )
        shape = _shape(len(source_types), source_types, target_type)
        structural_truth.append(shape)
        usage_truth.append({"usage": transition["usage"], **shape})

    modes = forecast["candidate_modes"]
    graph_candidates = {
        row["signature_id"]: row for row in modes["dependency_graph"]
    }
    no_edge_candidates = {
        row["signature_id"]: row for row in modes["without_edges"]
    }
    usage_candidates = {
        row["signature_id"]: row for row in modes["dependency_graph_with_usage"]
    }
    summary = {
        "dependency_graph": _score(set(graph_candidates), structural_truth),
        "without_edges": _score(set(no_edge_candidates), structural_truth),
        "dependency_graph_with_usage": _score(set(usage_candidates), usage_truth),
    }
    top_k = {}
    for budget in (20, 50, 100):
        graph_ranked = {
            row["signature_id"]: set(row["article_support"])
            for row in modes["dependency_graph"]
        }
        graph_catalog = {
            row["signature_id"]: row["shape"] for row in modes["dependency_graph"]
        }
        no_edge_ranked = {
            row["signature_id"]: set(row["article_support"])
            for row in modes["without_edges"]
        }
        no_edge_catalog = {
            row["signature_id"]: row["shape"] for row in modes["without_edges"]
        }
        top_k[str(budget)] = {
            "dependency_graph": _top_k_score(
                graph_ranked, graph_catalog, structural_truth, budget
            ),
            "without_edges": _top_k_score(
                no_edge_ranked, no_edge_catalog, structural_truth, budget
            ),
        }
    exact_graph_budget = _top_k_score(
        {
            row["signature_id"]: set(row["article_support"])
            for row in modes["without_edges"]
        },
        {
            row["signature_id"]: row["shape"] for row in modes["without_edges"]
        },
        structural_truth,
        len(graph_candidates),
    )
    truth_by_id = {_shape_id(shape): shape for shape in structural_truth}
    matched = []
    for signature_id in sorted(set(graph_candidates) & set(truth_by_id)):
        matched.append({
            "shape": truth_by_id[signature_id],
            "article_support": graph_candidates[signature_id]["article_support"],
        })
    return {
        "target": {
            "article_id": target_article["article_id"],
            **target_meta,
        },
        "forecast_sha256": forecast["forecast_sha256"],
        "target_transition_count_with_arity_1_to_3": len(structural_truth),
        "target_unique_shape_count": len({_shape_id(shape) for shape in structural_truth}),
        "mode_summary": summary,
        "top_k": {
            str(key): {
                mode: {k: v for k, v in row.items() if k != "selected_support"}
                for mode, row in values.items()
            }
            for key, values in top_k.items()
        },
        "without_edges_at_graph_candidate_budget": {
            key: value for key, value in exact_graph_budget.items()
            if key != "selected_support"
        },
        "matched_structural_forms": matched,
        "technical_validation": {
            "forecast_sealed_before_target_graph_read": True,
            "target_dag_validated": True,
            "target_source_hash_verified": True,
            "target_map_hash_verified": True,
            "target_schema_version": target_article["graph_schema_version"],
            "target_run_id": target_article["run_id"],
            "target_graph_sha256": target_meta["graph_sha256"],
        },
        "scientific_content_predicted": False,
        "expert_scientific_validation": False,
        "model_calls": 0,
        "network_calls": 0,
    }


def _render_ru(forecast: dict, evaluation: dict) -> str:
    modes = evaluation["mode_summary"]
    graph = modes["dependency_graph"]
    no_edge = modes["without_edges"]
    exact_usage = modes["dependency_graph_with_usage"]
    graph_budget = evaluation["without_edges_at_graph_candidate_budget"]
    lines = [
        "# Запечатанный свободный прогноз форм переходов PMC10000452",
        "",
        "**Это прогноз типов структуры связей, не содержательных утверждений статьи.** 19 обучающих карт взяты из зафиксированного манифеста. Сама цель и её граф не участвовали в построении кандидатов; файл прогноза сохранён до чтения целевой карты. Прямо цитирующие цель источники исключены из обучения.",
        "",
        f"Обучающих статей после фильтров: {forecast['training_article_count']}; исключено прямых цитат: {len(forecast['direct_citation_exclusions'])}; явно исключено источников той же когорты: {len(forecast['explicit_source_exclusions'])}. Для поддержки требовалось минимум {forecast['minimum_article_support']} разных публикации. Рассматривались связи с одной–тремя предпосылками.",
        "",
        "## Результат на удержанной цели",
        "",
        "| Режим | Кандидатов | Уникальных форм цели | Совпало | Точность | Полнота |",
        "|---|---:|---:|---:|---:|---:|",
        f"| Направленные формы графа | {graph['predicted_shape_count']} | {graph['target_shape_count']} | {graph['matched_shape_count']} | {graph['precision']:.3f} | {graph['recall']:.3f} |",
        f"| Типы блоков без связей | {no_edge['predicted_shape_count']} | {no_edge['target_shape_count']} | {no_edge['matched_shape_count']} | {no_edge['precision']:.3f} | {no_edge['recall']:.3f} |",
        f"| Формы графа с точной меткой применения | {exact_usage['predicted_shape_count']} | {exact_usage['target_shape_count']} | {exact_usage['matched_shape_count']} | {exact_usage['precision']:.3f} | {exact_usage['recall']:.3f} |",
        "",
        "Последняя строка требует дополнительного совпадения метки применения и потому имеет другое пространство форм. Для сравнения режимов без и с рёбрами используются первые две строки.",
        "",
        "## Одинаковый лимит кандидатов",
        "",
        "| Максимум форм | Режим | Выдано | Совпало | Точность | Полнота |",
        "|---:|---|---:|---:|---:|---:|",
    ]
    for budget, rows in evaluation["top_k"].items():
        for mode, label in (
            ("dependency_graph", "Граф"),
            ("without_edges", "Без связей"),
        ):
            row = rows[mode]
            lines.append(
                f"| {budget} | {label} | {row['predicted_shape_count']} | "
                f"{row['matched_shape_count']} | {row['precision']:.3f} | "
                f"{row['recall']:.3f} |"
            )
    lines.extend([
        "",
        f"При лимите, равном числу всех графовых кандидатов ({graph['predicted_shape_count']}), безрёберный режим совпал с {graph_budget['matched_shape_count']} целевыми формами из {graph_budget['predicted_shape_count']} (точность {graph_budget['precision']:.3f}); графовый режим совпал с {graph['matched_shape_count']} из {graph['predicted_shape_count']} (точность {graph['precision']:.3f}).",
        "",
        "## Что именно совпало",
        "",
        "| Форма предпосылок → результата | Поддержавшие статьи |",
        "|---|---|",
    ])
    for row in evaluation["matched_structural_forms"]:
        shape = row["shape"]
        sources = ", ".join(_type_ru(value) for value in shape["source_types"])
        lines.append(
            f"| {sources} → {_type_ru(shape['target_type'])}; "
            f"предпосылок: {shape['arity']} | {', '.join(row['article_support'])} |"
        )
    if not evaluation["matched_structural_forms"]:
        lines.append("| Совпавших форм нет | — |")
    lines.extend([
        "",
        "## Интерпретация и границы",
        "",
        "Этот тест показывает только то, что направленные типы переходов из 19 зависимых статей могут ранжировать некоторые формы переходов целевой карты точнее перечня совместно встречающихся типов. Он не предсказывает конкретные знания, значения, направление эффекта или выводы PMC10000452. Содержательная формализация остается отдельной нерешенной частью цели.",
        "",
        "Совпадение формы не является силлогизмом, доказательством причинности или подтверждением одной из 24 категорических схем. Силлогизмы и другие логические операции применимы только к явно подходящим посылкам; этот запуск их не использует.",
        "",
        "Проверка ретроспективная. PMC8775386 относится к той же Cretan Aging Cohort, что и целевая статья; для оценки независимого переноса её нужно исключить и пересчитать. Другие источники также могут иметь общие когорты или непрямую зависимость. Связи, не обнаруженные по DOI, PMCID или полному заголовку, могли остаться в обучении. Экспертная научная проверка не проводилась.",
        "",
        f"Прогноз запечатан до чтения целевого графа. Целевой запуск: {evaluation['technical_validation']['target_run_id']}. Хеш запечатанного прогноза: {evaluation['forecast_sha256']}. Модельных и сетевых вызовов: 0.",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Запечатанный свободный прогноз форм переходов PMC10000452")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--target-source", type=Path, default=TARGET_SOURCE_PATH)
    parser.add_argument("--target-map", type=Path, default=TARGET_MAP_PATH)
    parser.add_argument(
        "--exclude-article-id",
        action="append",
        default=[],
        help="Идентификатор карты, заранее исключаемой из обучающего корпуса",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    implementation = Path(__file__).read_bytes()
    implementation_sha256 = _sha(implementation)
    forecast = _build_forecast(args.manifest, tuple(args.exclude_article_id))
    forecast["implementation_sha256"] = implementation_sha256
    forecast["forecast_run_id"] = fingerprint({
        "version": VERSION,
        "training_manifest_sha256": forecast["training_manifest"]["sha256"],
        "target_source_sha256": TARGET_SOURCE_SHA256,
        "implementation_sha256": implementation_sha256,
        "minimum_support": MINIMUM_PUBLICATION_SUPPORT,
        "maximum_arity": MAXIMUM_ARITY,
    })
    args.output.mkdir(parents=True, exist_ok=False)
    forecast_bytes = _json_bytes(forecast)
    (args.output / "forecast.sealed.json").write_bytes(forecast_bytes)
    forecast_sha256 = _sha(forecast_bytes)
    forecast["forecast_sha256"] = forecast_sha256
    seal = {
        "version": VERSION,
        "forecast_sha256": forecast_sha256,
        "target_source_sha256": TARGET_SOURCE_SHA256,
        "target_graph_read_before_seal": False,
        "implementation_sha256": implementation_sha256,
        "model_calls": 0,
        "network_calls": 0,
    }
    (args.output / "seal.json").write_text(
        json.dumps(seal, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    target, target_meta = _target_truth(args.target_map, args.target_source)
    evaluation = _evaluate(forecast, target, target_meta)
    evaluation["report_ru_md"] = _render_ru(forecast, evaluation)
    (args.output / "evaluation.json").write_text(
        json.dumps(evaluation, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (args.output / "report.ru.md").write_text(evaluation["report_ru_md"], encoding="utf-8")
    (args.output / "implementation.py").write_bytes(implementation)
    verification = {
        **seal,
        "forecast_file_sha256": _sha((args.output / "forecast.sealed.json").read_bytes()),
        "evaluation_file_sha256": _sha((args.output / "evaluation.json").read_bytes()),
        "implementation_sha256": _sha(implementation),
        "target_map_file_sha256": target_meta["map_file_sha256"],
        "target_graph_sha256": target_meta["graph_sha256"],
        "target_dag_validated": True,
    }
    (args.output / "verification.json").write_text(
        json.dumps(verification, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "output": str(args.output),
        "forecast_sha256": seal["forecast_sha256"],
        "training_articles": forecast["training_article_count"],
        "direct_citation_exclusions": len(forecast["direct_citation_exclusions"]),
        "explicit_source_exclusions": len(forecast["explicit_source_exclusions"]),
        "graph": evaluation["mode_summary"]["dependency_graph"],
        "without_edges": evaluation["mode_summary"]["without_edges"],
        "target_graph_read_before_seal": False,
        "model_calls": 0,
        "network_calls": 0,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()

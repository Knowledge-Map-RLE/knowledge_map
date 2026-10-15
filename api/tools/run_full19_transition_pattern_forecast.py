"""Проверяет свободный перенос форм переходов между отложенными картами."""
from __future__ import annotations

import argparse
import itertools
import json
import re
from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path

from domain.article_maps import fingerprint, require
from domain.development_prediction import validate_visible_dag


ROOT = Path(r"D:\Knowledge_Map")
DEFAULT_MANIFEST = ROOT / (
    "eval/whole_map_forecast/semantic-parts-v1/"
    "full-corpus-19-prepared-v1/source-manifest.json"
)
VERSION = "full19-free-transition-pattern-citation-holdout-v5"
MINIMUM_PUBLICATION_SUPPORT = 2
MAXIMUM_ARITY = 3
TARGET_SOURCE_SHA256 = "f7df96ff746be4a60a6930ff2c5c25435725d0591dfe1f492259624b2d7c0bc8"
DOI_RE = re.compile(r"\b(10\.\d{4,9}/[A-Z0-9._;()/:+-]+)", re.IGNORECASE)
PMCID_RE = re.compile(r"\bPMC\d+\b", re.IGNORECASE)
TOKEN_RE = re.compile(r"[a-z0-9]+")
TYPE_RU = {
    "action": "действие",
    "state": "состояние",
    "assertion": "утверждение",
    "comparison": "сравнение",
    "conclusion": "вывод",
    "definition": "определение",
    "goal": "цель",
    "limitation": "ограничение",
    "method": "метод",
    "observation": "наблюдение",
    "operation": "операция",
    "result": "результат",
    "rule": "правило",
}
USAGE_RU = {
    "condition": "условие",
    "data": "данные",
    "definition": "определение",
    "development": "развитие",
    "evidence": "свидетельство",
    "method": "метод",
    "premise": "посылка",
    "prerequisite": "предпосылка",
    "result": "результат",
}


def _sha(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def _normal_text(text: str) -> str:
    text = text.casefold().replace("\u00ad", "")
    text = re.sub(r"[\u2010-\u2015\u2212]", "-", text)
    return " ".join(TOKEN_RE.findall(text))


def _article_citation_keys(article: dict, article_id: str) -> dict:
    text = article["source"]["text"]
    doi_match = DOI_RE.search(text)
    doi = doi_match.group(1).rstrip(".,;:").casefold() if doi_match else None
    headings = re.findall(r"(?m)^#\s+(.+?)\s*$", text)
    title = headings[0].strip() if headings else ""
    title_tokens = TOKEN_RE.findall(title.casefold())
    pmcids = PMCID_RE.findall(article_id)
    own_pmcid = pmcids[-1].casefold() if pmcids else None
    return {
        "doi": doi,
        "title": title,
        "title_key": " ".join(title_tokens),
        "own_pmcid": own_pmcid,
    }


def _citation_matches(target: dict, source: dict) -> list[dict]:
    source_text = source["source_text"]
    haystack = _normal_text(source_text)
    matches = []
    keys = target["citation_keys"]
    markers = []
    if keys["doi"]:
        markers.append(("doi", keys["doi"], _normal_text(keys["doi"])))
    if keys["own_pmcid"]:
        markers.append(("pmcid", keys["own_pmcid"], _normal_text(keys["own_pmcid"])))
    title_key = keys["title_key"]
    if len(title_key) >= 40 and len(title_key.split()) >= 6:
        markers.append(("exact_title", keys["title"], title_key))
    for kind, value, marker in markers:
        offset = haystack.find(marker)
        if offset >= 0:
            start = max(0, offset - 120)
            end = min(len(haystack), offset + len(marker) + 160)
            matches.append({
                "kind": kind,
                "value": value,
                "offset_encoding": "normalized_source_text_codepoints",
                "start": offset,
                "end": offset + len(marker),
                "snippet": haystack[start:end],
            })
    return matches


def _shape(arity: int, source_types: list[str], target_type: str) -> dict:
    return {
        "arity": arity,
        "source_types": sorted(source_types),
        "target_type": target_type,
    }


def _shape_id(shape: dict) -> str:
    return fingerprint(shape)


def _usage_shape(shape: dict, usage: str) -> dict:
    return {"usage": usage, **shape}


def _type_ru(value: str) -> str:
    kind, knowledge_kind = value.split("/", 1)
    return f"{TYPE_RU.get(kind, kind)}/{TYPE_RU.get(knowledge_kind, knowledge_kind)}"


def _structure_from_usage_signature(signature: dict) -> dict:
    return _shape(
        signature["arity"],
        signature["source_types"],
        signature["target_type"],
    )


def _load_articles(manifest_path: Path) -> tuple[dict[str, dict], dict]:
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes.decode("utf-8"))
    articles: dict[str, dict] = {}
    for entry in manifest["sources"]:
        raw = Path(entry["path"]).read_bytes()
        require(_sha(raw) == entry["file_sha256"], "Хеш карты не совпал с манифестом")
        article = json.loads(raw.decode("utf-8"))
        article_id = article["article_id"]
        require(article_id == entry["reference"]["article_id"], "Идентификатор статьи не совпал")
        require(article_id not in articles, "В манифесте повторяется статья")
        require(article["graph_schema_version"] == 6, "Требуется карта схемы 6")
        graph = article["graph"]
        require(fingerprint(graph) == entry["graph_sha256"], "Хеш графа не совпал с манифестом")
        validate_visible_dag(graph)
        nodes = {node["id"]: node["knowledge_id"] for node in graph["nodes"]}
        knowledge = {item["knowledge_id"]: item for item in graph["knowledge"]}
        node_types = Counter(
            f"{knowledge[node['knowledge_id']]['kind']}/"
            f"{knowledge[node['knowledge_id']]['knowledge_kind']}"
            for node in graph["nodes"]
        )
        shapes: list[dict] = []
        usage_shapes: list[dict] = []
        for transition in graph["transitions"]:
            source_types = [
                f"{knowledge[nodes[node_id]]['kind']}/"
                f"{knowledge[nodes[node_id]]['knowledge_kind']}"
                for node_id in transition["sources"]
            ]
            arity = len(source_types)
            if arity > MAXIMUM_ARITY:
                continue
            target_type = (
                f"{knowledge[nodes[transition['target']]]['kind']}/"
                f"{knowledge[nodes[transition['target']]]['knowledge_kind']}"
            )
            shape = _shape(arity, source_types, target_type)
            shapes.append(shape)
            usage = transition.get("usage")
            require(isinstance(usage, str) and usage.strip(), "У перехода нет метки применения")
            usage_shapes.append(_usage_shape(shape, usage))
        articles[article_id] = {
            "article_id": article_id,
            "raw_sha256": _sha(raw),
            "graph_sha256": entry["graph_sha256"],
            "source_sha256": entry["source_sha256"],
            "source_text": article["source"]["text"],
            "citation_keys": _article_citation_keys(article, article_id),
            "node_type_counts": node_types,
            "shapes": shapes,
            "usage_shapes": usage_shapes,
            "family": entry.get("family", article_id),
            "title": entry.get("title"),
        }
    require(len(articles) == len(manifest["sources"]), "Число загруженных карт не совпало")
    require(
        all(entry["source_sha256"] != TARGET_SOURCE_SHA256 for entry in manifest["sources"]),
        "Целевая PMC10000452 обнаружена среди обучающих входов",
    )
    return articles, {
        "sha256": _sha(manifest_bytes),
        "source_count": len(articles),
        "path": str(manifest_path),
    }


def _graph_predictions(training: dict[str, dict]) -> tuple[set[str], dict[str, set[str]]]:
    supports: dict[str, set[str]] = defaultdict(set)
    for article_id, row in training.items():
        for shape in row["shapes"]:
            supports[_shape_id(shape)].add(article_id)
    eligible = {
        signature_id: sources
        for signature_id, sources in supports.items()
        if len(sources) >= MINIMUM_PUBLICATION_SUPPORT
    }
    return set(eligible), eligible


def _usage_predictions(training: dict[str, dict]) -> tuple[set[str], dict[str, set[str]]]:
    supports: dict[str, set[str]] = defaultdict(set)
    for article_id, row in training.items():
        for signature in row["usage_shapes"]:
            supports[fingerprint(signature)].add(article_id)
    eligible = {
        signature_id: sources
        for signature_id, sources in supports.items()
        if len(sources) >= MINIMUM_PUBLICATION_SUPPORT
    }
    return set(eligible), eligible


def _cooccurrence_details(
    training: dict[str, dict],
) -> tuple[set[str], dict[str, set[str]], dict[str, dict]]:
    supports: dict[str, set[str]] = defaultdict(set)
    catalog: dict[str, dict] = {}
    for article_id, row in training.items():
        counts = row["node_type_counts"]
        types = sorted(counts)
        for arity in range(1, MAXIMUM_ARITY + 1):
            for source_types in itertools.combinations_with_replacement(types, arity):
                source_counts = Counter(source_types)
                for target_type in types:
                    required = source_counts + Counter({target_type: 1})
                    if all(counts[key] >= count for key, count in required.items()):
                        signature = _shape(arity, list(source_types), target_type)
                        signature_id = _shape_id(signature)
                        supports[signature_id].add(article_id)
                        catalog[signature_id] = signature
    eligible = {
        signature_id: sources
        for signature_id, sources in supports.items()
        if len(sources) >= MINIMUM_PUBLICATION_SUPPORT
    }
    return set(eligible), eligible, catalog


def _cooccurrence_predictions(training: dict[str, dict]) -> tuple[set[str], dict[str, set[str]]]:
    candidates, support, _ = _cooccurrence_details(training)
    return candidates, support


def _top_k_score(
    support: dict[str, set[str]],
    catalog: dict[str, dict],
    truth: list[dict],
    budget: int,
) -> dict:
    ranked = sorted(support, key=lambda key: (-len(support[key]), key))
    selected = set(ranked[:budget])
    result = _score(selected, truth)
    result["budget"] = budget
    result["selected_support"] = [
        {"shape_id": key, "article_support": len(support[key]), "shape": catalog[key]}
        for key in ranked[:budget]
    ]
    return result


def _aggregate_scores(scores: list[dict]) -> dict:
    keys = (
        "predicted_shape_count", "target_shape_count", "matched_shape_count",
        "missed_shape_count", "extra_shape_count", "target_transition_count",
        "covered_target_transition_count",
    )
    totals = {key: sum(score[key] for score in scores) for key in keys}
    predicted = totals["predicted_shape_count"]
    targets = totals["target_shape_count"]
    totals["precision"] = totals["matched_shape_count"] / predicted if predicted else 0.0
    totals["recall"] = totals["matched_shape_count"] / targets if targets else 0.0
    totals["fold_count"] = len(scores)
    return totals


def _paired_comparison(folds: list[dict], budget: str) -> dict:
    wins = losses = ties = graph_hits = no_edge_hits = 0
    for fold in folds:
        graph = fold["top_k_scores"][budget]["edge_patterns"]
        no_edge = fold["top_k_scores"][budget]["cooccurrence"]
        graph_hits += graph["matched_shape_count"]
        no_edge_hits += no_edge["matched_shape_count"]
        if graph["matched_shape_count"] > no_edge["matched_shape_count"]:
            wins += 1
        elif graph["matched_shape_count"] < no_edge["matched_shape_count"]:
            losses += 1
        else:
            ties += 1
    return {
        "budget_per_fold": int(budget),
        "graph_wins": wins,
        "no_edge_wins": losses,
        "ties": ties,
        "graph_matched_shapes": graph_hits,
        "no_edge_matched_shapes": no_edge_hits,
    }


def _citation_exclusions(articles: dict[str, dict]) -> dict[str, list[dict]]:
    exclusions = {}
    for target_id, target in articles.items():
        matches = []
        for source_id, source in articles.items():
            if source_id == target_id:
                continue
            found = _citation_matches(target, source)
            if found:
                matches.append({
                    "citing_article_id": source_id,
                    "citation_evidence": found,
                    "citing_source_sha256": source["source_sha256"],
                })
        exclusions[target_id] = matches
    return exclusions


def _score(prediction_ids: set[str], truth: list[dict]) -> dict:
    truth_counts = Counter(_shape_id(shape) for shape in truth)
    truth_ids = set(truth_counts)
    hits = prediction_ids & truth_ids
    return {
        "predicted_shape_count": len(prediction_ids),
        "target_shape_count": len(truth_ids),
        "matched_shape_count": len(hits),
        "missed_shape_count": len(truth_ids - prediction_ids),
        "extra_shape_count": len(prediction_ids - truth_ids),
        "precision": len(hits) / len(prediction_ids) if prediction_ids else 0.0,
        "recall": len(hits) / len(truth_ids) if truth_ids else 0.0,
        "matched_shapes": sorted(hits),
        "target_transition_count": len(truth),
        "covered_target_transition_count": sum(truth_counts[key] for key in hits),
        "target_transition_coverage": (
            sum(truth_counts[key] for key in hits) / len(truth) if truth else 0.0
        ),
    }


def run(manifest_path: Path) -> dict:
    articles, manifest_meta = _load_articles(manifest_path)
    exclusions = _citation_exclusions(articles)
    folds = []
    shape_catalog: dict[str, dict] = {}
    usage_catalog: dict[str, dict] = {}
    pooled = {
        "edge_patterns": Counter(),
        "cooccurrence": Counter(),
        "edge_patterns_with_usage": Counter(),
    }
    top_k = {str(k): {"edge_patterns": [], "cooccurrence": []} for k in (20, 50, 100)}
    matched_budget_no_edge = []
    match_examples = []
    for target_id, target in sorted(articles.items()):
        excluded_ids = {item["citing_article_id"] for item in exclusions[target_id]}
        training = {
            article_id: article for article_id, article in articles.items()
            if article_id != target_id and article_id not in excluded_ids
        }
        edge_predictions, edge_support = _graph_predictions(training)
        usage_predictions, usage_support = _usage_predictions(training)
        no_edge_predictions, no_edge_support, no_edge_catalog = _cooccurrence_details(training)
        edge_catalog = {
            _shape_id(shape): shape
            for row in training.values()
            for shape in row["shapes"]
        }
        shape_catalog.update(edge_catalog)
        shape_catalog.update(no_edge_catalog)
        for row in training.values():
            for signature in row["usage_shapes"]:
                usage_catalog[fingerprint(signature)] = signature
        truth = target["shapes"]
        usage_truth = target["usage_shapes"]
        scored = {
            "edge_patterns": _score(edge_predictions, truth),
            "cooccurrence": _score(no_edge_predictions, truth),
            "edge_patterns_with_usage": _score(usage_predictions, usage_truth),
        }
        fold_top_k = {}
        for budget in (20, 50, 100):
            graph_top = _top_k_score(edge_support, edge_catalog, truth, budget)
            no_edge_top = _top_k_score(no_edge_support, no_edge_catalog, truth, budget)
            top_k[str(budget)]["edge_patterns"].append(graph_top)
            top_k[str(budget)]["cooccurrence"].append(no_edge_top)
            fold_top_k[str(budget)] = {
                "edge_patterns": {
                    key: value for key, value in graph_top.items()
                    if key != "selected_support"
                },
                "cooccurrence": {
                    key: value for key, value in no_edge_top.items()
                    if key != "selected_support"
                },
            }
        graph_budget = len(edge_predictions)
        no_edge_same_budget = _top_k_score(
            no_edge_support, no_edge_catalog, truth, graph_budget
        )
        matched_budget_no_edge.append(no_edge_same_budget)
        fold_top_k["no_edge_at_graph_candidate_budget"] = {
            key: value for key, value in no_edge_same_budget.items()
            if key != "selected_support"
        }
        for mode, score_key in (
            ("edge_patterns", "edge_patterns"),
            ("cooccurrence", "cooccurrence"),
            ("edge_patterns_with_usage", "edge_patterns_with_usage"),
        ):
            for key in (
                "predicted_shape_count", "target_shape_count", "matched_shape_count",
                "missed_shape_count", "extra_shape_count", "target_transition_count",
                "covered_target_transition_count",
            ):
                pooled[mode][key] += scored[score_key][key]
        truth_by_id = {_shape_id(shape): shape for shape in truth}
        for shape_id in sorted(set(edge_predictions) & set(truth_by_id)):
            match_examples.append({
                "target_article_id": target_id,
                "shape": truth_by_id[shape_id],
                "training_support": sorted(edge_support[shape_id]),
                "usage_variants_in_target": sorted({
                    item["usage"] for item in usage_truth
                    if _shape_id(_structure_from_usage_signature(item)) == shape_id
                }),
            })
        folds.append({
            "target_article_id": target_id,
            "target_title": target["citation_keys"]["title"],
            "target_source_sha256": target["source_sha256"],
            "target_graph_sha256": target["graph_sha256"],
            "excluded_citing_sources": exclusions[target_id],
            "training_article_count": len(training),
            "training_article_ids": sorted(training),
            "target_transition_count_arity_1_to_3": len(truth),
            "target_unique_shape_count": len({_shape_id(shape) for shape in truth}),
            "mode_scores": scored,
            "top_k_scores": fold_top_k,
            "predicted_edge_shapes": [
                {"shape_id": key, "training_support": sorted(edge_support[key])}
                for key in sorted(edge_predictions)
            ],
            "predicted_no_edge_shapes": [
                {"shape_id": key, "training_support": sorted(no_edge_support[key])}
                for key in sorted(no_edge_predictions)
            ],
            "predicted_edge_shapes_with_usage": [
                {"signature_id": key, "training_support": sorted(usage_support[key])}
                for key in sorted(usage_predictions)
            ],
        })
    summary = {}
    for mode, counters in pooled.items():
        predicted = counters["predicted_shape_count"]
        targets = counters["target_shape_count"]
        hits = counters["matched_shape_count"]
        summary[mode] = {
            **dict(counters),
            "precision": hits / predicted if predicted else 0.0,
            "recall": hits / targets if targets else 0.0,
            "minimum_support_articles": MINIMUM_PUBLICATION_SUPPORT,
        }
    top_k_summary = {
        budget: {
            mode: _aggregate_scores(scores)
            for mode, scores in modes.items()
        }
        for budget, modes in top_k.items()
    }
    top_k_summary["no_edge_at_graph_candidate_budget"] = _aggregate_scores(
        matched_budget_no_edge
    )
    paired_top_k = {
        budget: _paired_comparison(folds, budget)
        for budget in ("20", "50", "100")
    }
    return {
        "version": VERSION,
        "manifest": manifest_meta,
        "source_count": len(articles),
        "target_source_excluded": True,
        "target_source_sha256_excluded": TARGET_SOURCE_SHA256,
        "citation_exclusion_method": [
            "точное совпадение DOI",
            "точное совпадение PMCID, если он присутствует в идентификаторе карты",
            "точное совпадение полного заголовка длиной не менее шести слов",
        ],
        "unseen_or_transitive_citations_not_ruled_out": True,
        "model_calls": 0,
        "network_calls": 0,
        "minimum_publication_support": MINIMUM_PUBLICATION_SUPPORT,
        "maximum_transition_arity": MAXIMUM_ARITY,
        "signature_definition": (
            "arity + multiset(source kind/knowledge_kind) + target kind/knowledge_kind; "
            "метка применения оценивается отдельно"
        ),
        "modes": {
            "edge_patterns": "свободно предсказанный повторяемый типизированный переход из графа",
            "cooccurrence": "свободная комбинация типов знаний из одних и тех же статей без рёбер",
            "edge_patterns_with_usage": "тот же переход вместе с авторской меткой usage",
        },
        "pooled_summary": summary,
        "top_k_summary": top_k_summary,
        "paired_top_k": paired_top_k,
        "prediction_catalog": {
            "structural_shapes": shape_catalog,
            "usage_shapes": usage_catalog,
        },
        "citation_exclusions": exclusions,
        "folds": folds,
        "matched_pattern_examples": match_examples,
        "interpretation_limits": [
            "Оценивается форма перехода между классами блоков, а не содержание научного утверждения.",
            "Публикации могут использовать одну когорту или цитировать друг друга через нераспознанные формы.",
            "Совпавший паттерн не является логическим правилом и не получает лицензии на перенос фактов.",
            "Минимальная поддержка по публикациям не доказывает независимость источников.",
        ],
    }


def render_ru(result: dict) -> str:
    summary = result["pooled_summary"]
    edge = summary["edge_patterns"]
    no_edge = summary["cooccurrence"]
    usage = summary["edge_patterns_with_usage"]
    top_k_summary = result["top_k_summary"]
    lines = [
        "# Свободный прогноз форм переходов на 19 картах",
        "",
        "**Проверяется перенос структуры, не предсказание научного содержания.** Для каждого источника его карта целиком удерживалась от обучения. Из обучения исключались источники, в полном тексте которых найдены DOI, PMCID или полный заголовок удержанной статьи.",
        "",
        f"Проверено карт: {result['source_count']}. Целевая PMC10000452 исключена. Связи с арностью свыше {result['maximum_transition_arity']} не включены. Для вывода кандидата требовалась поддержка минимум в {result['minimum_publication_support']} разных статьях.",
        "",
        "## Сравнение графа зависимостей и контроля без связей",
        "",
        "| Режим | Предсказано форм | Форм в целевых статьях | Совпало | Точность | Полнота | Покрыто переходов цели |",
        "|---|---:|---:|---:|---:|---:|---:|",
        f"| Повторяемые переходы исходного графа | {edge['predicted_shape_count']} | {edge['target_shape_count']} | {edge['matched_shape_count']} | {edge['precision']:.3f} | {edge['recall']:.3f} | {edge['covered_target_transition_count']}/{edge['target_transition_count']} |",
        f"| Совместная встречаемость типов без рёбер | {no_edge['predicted_shape_count']} | {no_edge['target_shape_count']} | {no_edge['matched_shape_count']} | {no_edge['precision']:.3f} | {no_edge['recall']:.3f} | {no_edge['covered_target_transition_count']}/{no_edge['target_transition_count']} |",
        f"| Переходы с точной меткой применения | {usage['predicted_shape_count']} | {usage['target_shape_count']} | {usage['matched_shape_count']} | {usage['precision']:.3f} | {usage['recall']:.3f} | {usage['covered_target_transition_count']}/{usage['target_transition_count']} |",
        "",
        "Первые две строки используют один формат оценки: число предпосылок, их типы и тип результата. Графовый режим учит направленные группы из самих карт. Контроль без связей перечисляет комбинации типов, совместно присутствующих в статье. Третья строка дополнительно требует совпадения метки применения, поэтому её число форм нельзя напрямую сравнивать с первыми двумя.",
        "",
        "## Сравнение при равном предельном бюджете",
        "",
        "| Максимум форм на статью | Режим | Выдано форм | Совпало | Точность | Полнота |",
        "|---:|---|---:|---:|---:|---:|",
    ]
    for budget, modes in top_k_summary.items():
        if budget == "no_edge_at_graph_candidate_budget":
            continue
        for mode, label in (
            ("edge_patterns", "Граф"),
            ("cooccurrence", "Без рёбер"),
        ):
            item = modes[mode]
            lines.append(
                f"| {budget} | {label} | {item['predicted_shape_count']} | "
                f"{item['matched_shape_count']} | {item['precision']:.3f} | "
                f"{item['recall']:.3f} |"
            )
    matched = top_k_summary["no_edge_at_graph_candidate_budget"]
    lines.extend([
        "",
        f"При бюджете, равном числу графовых кандидатов отдельно в каждом фолде, оба режима выдали по {edge['predicted_shape_count']} форм: граф совпал с {edge['matched_shape_count']}, безрёберный контроль — с {matched['matched_shape_count']} (точность {edge['precision']:.3f} против {matched['precision']:.3f}).",
        "",
        (
            f"При бюджете 20 форм на статью граф опередил контроль в "
            f"{result['paired_top_k']['20']['graph_wins']} фолдах, уступил в "
            f"{result['paired_top_k']['20']['no_edge_wins']} и сравнялся в "
            f"{result['paired_top_k']['20']['ties']}; суммарно совпало "
            f"{result['paired_top_k']['20']['graph_matched_shapes']} против "
            f"{result['paired_top_k']['20']['no_edge_matched_shapes']} форм. "
            "Это парное описательное сравнение; статьи не считаются независимыми."
        ),
        "",
        "## Примеры совпавших форм",
        "",
        "| Целевая статья | Предпосылки → результат | Поддержавшие обучающие статьи | Метки в цели |",
        "|---|---|---|---|",
    ])
    if result["matched_pattern_examples"]:
        for item in result["matched_pattern_examples"]:
            shape = item["shape"]
            lines.append(
                f"| {item['target_article_id']} | "
                f"{', '.join(_type_ru(value) for value in shape['source_types'])} → {_type_ru(shape['target_type'])} "
                f"(арность {shape['arity']}) | "
                f"{', '.join(item['training_support'])} | "
                f"{', '.join(USAGE_RU.get(value, value) for value in item['usage_variants_in_target']) or '—'} |"
            )
    else:
        lines.append("| — | Совпавших форм нет | — | — |")
    lines.extend([
        "",
        "## Интерпретация",
        "",
        "Если граф превосходит контроль без рёбер по точности или числу совпадений при сопоставимом объёме вывода, это диагностический признак, что направленные группы зависимостей помогают переносить схемы. Он не доказывает, что граф предсказывает новые выводы, и не означает, что блоки разных статей выражают одно знание.",
        "",
        "Шаблоны получены частотным переносом типизированных групп переходов с поддержкой минимум в двух источниках. Это не силлогизмы, не формальная логика и не отдельная операция мышления. Их следует проверять независимо на картах с пригодными посылками и известным контекстом.",
        "",
        "## Ограничения и воспроизводимость",
        "",
        "Фильтр ищет точный DOI, PMCID или полный заголовок; он может пропустить цитаты с иной записью и не исключает транзитивную зависимость через обзоры. Статьи могут анализировать общие когорты. Требуется независимая оценка содержания совпавших блоков и проверка на новых статьях, зафиксированных до раскрытия цели.",
        "",
        f"Версия алгоритма: {result['version']}. Манифест SHA-256: {result['manifest']['sha256']}. Модельных и сетевых вызовов: 0. Экспертная научная проверка не проводилась.",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Свободный тест повторяемых форм переходов")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.manifest)
    implementation = Path(__file__).read_bytes()
    result["implementation_sha256"] = _sha(implementation)
    result["run_id"] = fingerprint({
        "version": VERSION,
        "manifest_sha256": result["manifest"]["sha256"],
        "implementation_sha256": result["implementation_sha256"],
        "minimum_support": MINIMUM_PUBLICATION_SUPPORT,
        "maximum_arity": MAXIMUM_ARITY,
    })
    result["report_ru_md"] = render_ru(result)
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "data.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (args.output / "report.ru.md").write_text(result["report_ru_md"], encoding="utf-8")
    (args.output / "implementation.py").write_bytes(implementation)
    print(json.dumps({
        "run_id": result["run_id"],
        "output": str(args.output),
        "sources": result["source_count"],
        "edge": result["pooled_summary"]["edge_patterns"],
        "no_edge": result["pooled_summary"]["cooccurrence"],
        "usage": result["pooled_summary"]["edge_patterns_with_usage"],
        "model_calls": 0,
        "network_calls": 0,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()

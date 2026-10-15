"""Перенос структур авторских операторов без переноса численных научных выводов."""
from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from hashlib import sha256
import json
import random

from domain.article_maps import fingerprint, require
from domain.comparison_normalization import VERSION as NORMALIZER_VERSION, canonical, normalize_map
from domain.development_prediction import validate_visible_dag
from domain.operator_frame_routing import PREDICATES, VERSION as ROUTING_VERSION

VERSION = "schema6-operator-transition-lopo-1"
MODES = {"graph", "semantic_without_dependencies", "permuted_dependencies"}
DEFAULT_LIMIT = 20


def validate_map_snapshot(value: dict) -> None:
    """Проверяет схему, DAG и привязку всех используемых фрагментов к источнику."""
    require(isinstance(value, dict) and value.get("pipeline_id") == "text_reified",
            "Operator forecast requires a direct text-to-map snapshot")
    graph, source = value.get("graph"), value.get("source")
    require(isinstance(graph, dict) and graph.get("schema_version") == 6,
            "Operator forecast requires schema 6")
    require(isinstance(source, dict) and source.get("offset_encoding") == "unicode_codepoints",
            "Unicode source coordinates required")
    text = source.get("text")
    require(isinstance(text, str) and sha256(text.encode("utf-8")).hexdigest() == source.get("sha256"),
            "Source text hash differs")
    content_end = source.get("content_end")
    require(type(content_end) is int and 0 <= content_end <= len(text), "Invalid content boundary")
    units = {unit["id"]: unit for unit in source.get("units", [])}
    require(len(units) == len(source.get("units", [])), "Duplicate source unit")
    for unit in units.values():
        start, end = unit.get("start"), unit.get("end")
        require(type(start) is int and type(end) is int and 0 <= start < end <= len(text)
                and text[start:end] == unit.get("text"), "Source unit coordinates differ")

    validate_visible_dag(graph)
    knowledge = {item["knowledge_id"]: item for item in graph.get("knowledge", [])}
    nodes = {node["id"]: node["knowledge_id"] for node in graph.get("nodes", [])}
    require(len(knowledge) == len(graph.get("knowledge", [])) and len(nodes) == len(graph.get("nodes", [])),
            "Duplicate knowledge or occurrence id")
    require(set(nodes.values()) == set(knowledge), "Every canonical knowledge item needs a visible occurrence")
    transition_edges = set()
    for transition in graph.get("transitions", []):
        sources, target = transition.get("sources"), transition.get("target")
        require(isinstance(sources, list) and bool(sources) and len(sources) == len(set(sources))
                and target in nodes and target not in sources and all(source_id in nodes for source_id in sources),
                "Invalid author dependency group")
        transition_edges.update((source_id, target) for source_id in sources)
        for unit_id in transition.get("unit_ids", []):
            require(unit_id in units, "Unknown transition source unit")
    require(transition_edges == {(edge["source"], edge["target"]) for edge in graph.get("edges", [])},
            "Author dependency groups differ from visible edges")

    concepts = {concept["id"] for concept in graph.get("concepts", [])}
    for item in knowledge.values():
        for statement in item["semantic_frame"]["statements"]:
            for role in statement["roles"]:
                reference = role.get("concept_id") or role.get("knowledge_id")
                require(reference in (concepts if role.get("concept_id") else knowledge),
                        "Unknown semantic participant")
            for unit_id in statement["provenance"]["unit_ids"]:
                require(unit_id in units, "Unknown statement source unit")
                require(units[unit_id]["end"] <= content_end,
                        "Bibliography cannot support an operator pattern")

    # Нормализация дополнительно проверяет ссылки на канонические понятия и знания.
    normalize_map(value)


def _operator_profile(item: dict) -> dict:
    frame = item["semantic_frame"]
    statements = []
    for statement in frame["statements"]:
        predicate = " ".join(statement["predicate"].casefold().replace("_", " ").split())
        role_names = sorted(canonical(role["role"], "roles") for role in statement["roles"])
        statements.append({
            "operator_family": PREDICATES.get(predicate, "unregistered:" + predicate),
            "negated": statement["negated"],
            "modal": statement["modality"] is not None,
            "roles": role_names,
        })
    return {
        "kind": item["kind"],
        "action_status": item["action_status"],
        "knowledge_kind": item["knowledge_kind"],
        "logic": frame["logic"],
        "statements": sorted(statements, key=fingerprint),
    }


def _participants(item: dict) -> set[tuple[str, str]]:
    result = set()
    for statement in item["semantic_frame"]["statements"]:
        for role in statement["roles"]:
            if role["concept_id"]:
                result.add(("concept", role["concept_id"]))
            else:
                result.add(("knowledge", role["knowledge_id"]))
    return result


def _pattern(body: list[dict], head: dict) -> dict:
    ordered_body = sorted(body, key=fingerprint)
    value = {"arity": len(ordered_body), "premises": ordered_body, "conclusion": head}
    return {"id": fingerprint(value), **value}


def _single_author_groups(value: dict) -> list[dict]:
    graph = value["graph"]
    by_id = {item["knowledge_id"]: item for item in graph["knowledge"]}
    occurrence_to_knowledge = {node["id"]: node["knowledge_id"] for node in graph["nodes"]}
    rows = []
    for transition in graph["transitions"]:
        if len(transition["sources"]) != 1:
            continue
        premise_id = occurrence_to_knowledge[transition["sources"][0]]
        conclusion_id = occurrence_to_knowledge[transition["target"]]
        premise, conclusion = by_id[premise_id], by_id[conclusion_id]
        pattern = _pattern([_operator_profile(premise)], _operator_profile(conclusion))
        rows.append({"pattern": pattern, "premise_text": premise["display_text"],
                     "conclusion_text": conclusion["display_text"], "premise_id": premise_id,
                     "conclusion_id": conclusion_id})
    return rows


def _semantic_pairs(value: dict) -> list[dict]:
    """Строит направленные пары по общим участникам, не читая авторские рёбра."""
    items = value["graph"]["knowledge"]
    profiles = {item["knowledge_id"]: _operator_profile(item) for item in items}
    participants = {item["knowledge_id"]: _participants(item) for item in items}
    rows = []
    for head in items:
        head_id = head["knowledge_id"]
        for premise in items:
            premise_id = premise["knowledge_id"]
            if head_id == premise_id or not (participants[head_id] & participants[premise_id]):
                continue
            rows.append({"pattern": _pattern([profiles[premise_id]], profiles[head_id]),
                         "premise_text": premise["display_text"],
                         "conclusion_text": head["display_text"], "premise_id": premise_id,
                         "conclusion_id": head_id})
    return rows


def _permute_groups(normalized: list[dict], ranks: dict[str, dict], seed: int) -> tuple[list[dict], dict]:
    """Переставляет входы и сохраняет ограничения ацикличности исходной проверки."""
    result = deepcopy(normalized)
    by_article: dict[str, list[dict]] = defaultdict(list)
    for item in result:
        by_article[item["article_id"]].append(item)
    rng = random.Random(seed)
    stats = {"original_groups": 0, "permuted_groups": 0, "skipped_groups": 0,
             "original_premises": 0, "permuted_premises": 0, "changed_groups": 0}
    for target in result:
        groups = target["premise_groups"]
        if not groups:
            continue
        article, target_id = target["article_id"], target["id"]
        target_min = ranks[article][target_id]["min"]
        candidates = [item["id"] for item in by_article[article] if item["id"] != target_id
                      and ranks[article][item["id"]]["max"] < target_min]
        used, replacement = set(), []
        for group in groups:
            stats["original_groups"] += 1
            stats["original_premises"] += len(group)
            available = [candidate for candidate in candidates if candidate not in used]
            if len(available) < len(group):
                stats["skipped_groups"] += 1
                continue
            chosen = sorted(rng.sample(available, len(group)))
            used.update(chosen)
            replacement.append(chosen)
            stats["permuted_groups"] += 1
            stats["permuted_premises"] += len(chosen)
            stats["changed_groups"] += int(chosen != sorted(group))
        target["premise_groups"] = replacement
    return result, stats


def _permuted_author_groups(value: dict, seed: int,
                            normalized: list[dict] | None = None) -> tuple[list[dict], dict]:
    normalized = normalized if normalized is not None else normalize_map(value)
    rank_values: dict[str, list[int]] = defaultdict(list)
    for node in value["graph"]["nodes"]:
        rank_values[node["knowledge_id"]].append(node["rank"])
    ranks = {value["article_id"]: {knowledge_id: {"min": min(items), "max": max(items)}
                                   for knowledge_id, items in rank_values.items()}}
    shuffled, stats = _permute_groups(normalized, ranks, seed)
    knowledge = {item["knowledge_id"]: item for item in value["graph"]["knowledge"]}
    rows = []
    for item in shuffled:
        for group in item["premise_groups"]:
            if len(group) != 1:
                continue
            premise, conclusion = knowledge[group[0]], knowledge[item["id"]]
            rows.append({"pattern": _pattern([_operator_profile(premise)], _operator_profile(conclusion)),
                         "premise_text": premise["display_text"],
                         "conclusion_text": conclusion["display_text"], "premise_id": group[0],
                         "conclusion_id": item["id"]})
    return rows, stats


def patterns_for_map(value: dict, mode: str, seed: int = 0) -> tuple[list[dict], dict]:
    require(mode in MODES, "Unknown operator pattern mode")
    validate_map_snapshot(value)
    if mode == "graph":
        rows = _single_author_groups(value)
        return rows, {"source_group_count": len(value["graph"]["transitions"]),
                      "eligible_single_premise_groups": len(rows)}
    if mode == "semantic_without_dependencies":
        rows = _semantic_pairs(value)
        return rows, {"candidate_pair_count": len(rows), "author_dependencies_read": False}
    rows, stats = _permuted_author_groups(value, seed)
    return rows, stats


def forecast_from_rows(rows_by_article: dict[str, list[dict]], *, mode: str,
                       limit: int = DEFAULT_LIMIT, min_support: int = 1) -> dict:
    """Ранжирует только структурные шаблоны из переданных обучающих статей."""
    require(mode in MODES and type(limit) is int and limit > 0
            and type(min_support) is int and min_support >= 1, "Invalid operator forecast settings")
    grouped: dict[str, dict] = {}
    for article_id, rows in sorted(rows_by_article.items()):
        for row in rows:
            pattern = row["pattern"]
            item = grouped.setdefault(pattern["id"], {"pattern": pattern, "support_sources": set(),
                "frequency": 0, "examples": []})
            item["support_sources"].add(article_id)
            item["frequency"] += 1
            if len(item["examples"]) < 2:
                item["examples"].append({"article_id": article_id, "premise_text": row["premise_text"],
                    "conclusion_text": row["conclusion_text"], "premise_id": row["premise_id"],
                    "conclusion_id": row["conclusion_id"]})
    eligible = [(key, item) for key, item in grouped.items() if len(item["support_sources"]) >= min_support]
    eligible.sort(key=lambda pair: (-len(pair[1]["support_sources"]), -pair[1]["frequency"], pair[0]))
    candidates = [{"id": key, "pattern": item["pattern"],
                   "support_sources": sorted(item["support_sources"]),
                   "support": len(item["support_sources"]), "frequency": item["frequency"],
                   "examples": item["examples"], "status": "structural_operator_hypothesis",
                   "scientific_fact": False}
                  for key, item in eligible[:limit]]
    return {"version": VERSION, "mode": mode, "candidate_limit": limit, "minimum_publication_support": min_support,
            "training_source_ids": sorted(rows_by_article), "candidate_count_before_limit": len(eligible),
            "predictions": candidates, "scientific_fact_forecast": False, "model_calls": 0}


def forecast(training_maps: list[dict], *, mode: str, limit: int = DEFAULT_LIMIT,
             min_support: int = 1, seed: int = 0) -> dict:
    require(bool(training_maps), "Explicit training maps required")
    ids = [item["article_id"] for item in training_maps]
    require(len(ids) == len(set(ids)), "Duplicate training article")
    rows = {}
    diagnostics = {}
    for item in training_maps:
        patterns, stats = patterns_for_map(item, mode, seed + int(fingerprint(item["article_id"])[:8], 16))
        rows[item["article_id"]] = patterns
        diagnostics[item["article_id"]] = stats
    result = forecast_from_rows(rows, mode=mode, limit=limit, min_support=min_support)
    result["diagnostics_by_source"] = diagnostics
    result["routing_version"] = ROUTING_VERSION
    return result


def evaluate(forecast_result: dict, target_map: dict) -> dict:
    """Оценивает замороженный набор шаблонов по одному отложенному графу."""
    validate_map_snapshot(target_map)
    target_id = target_map["article_id"]
    require(target_id not in forecast_result["training_source_ids"], "Target article leaked into training")
    target_rows = _single_author_groups(target_map)
    target_counts = Counter(row["pattern"]["id"] for row in target_rows)
    predicted = {item["id"] for item in forecast_result["predictions"]}
    hits = predicted & set(target_counts)
    count = len(forecast_result["predictions"])
    target_patterns = len(target_counts)
    instances = sum(target_counts[key] for key in hits)
    return {"target_article_id": target_id, "candidate_count": count,
            "unique_operator_patterns_in_target": target_patterns,
            "unique_patterns_hit": len(hits), "target_transition_instances_hit": instances,
            "candidate_pattern_precision": len(hits) / count if count else None,
            "target_pattern_recall": len(hits) / target_patterns if target_patterns else None,
            "matched_pattern_ids": sorted(hits), "target_transition_count": len(target_rows),
            "target_excluded_from_training": True, "target_read_order_verified": False,
            "scientific_claims_evaluated": False}


def run_lopo(maps: list[dict], *, candidate_limit: int = DEFAULT_LIMIT,
             min_support: int = 1, permuted_seeds: list[int] | None = None) -> dict:
    """Строит прогнозы на каждом fold до чтения соответствующей отложенной карты."""
    require(bool(maps), "Explicit corpus maps required")
    for item in maps:
        validate_map_snapshot(item)
    by_id = {item["article_id"]: item for item in maps}
    require(len(by_id) == len(maps), "Duplicate article in LOPO corpus")
    normalized_by_source = {article_id: normalize_map(by_id[article_id]) for article_id in sorted(by_id)}
    modes = ("graph", "semantic_without_dependencies")
    source_rows: dict[str, dict[str, list[dict]]] = {mode: {} for mode in modes}
    diagnostics: dict[str, dict[str, dict]] = {mode: {} for mode in modes}
    for article_id in sorted(by_id):
        value = by_id[article_id]
        graph_rows = _single_author_groups(value)
        source_rows["graph"][article_id] = graph_rows
        diagnostics["graph"][article_id] = {
            "source_group_count": len(value["graph"]["transitions"]),
            "eligible_single_premise_groups": len(graph_rows),
        }
        semantic_rows = _semantic_pairs(value)
        source_rows["semantic_without_dependencies"][article_id] = semantic_rows
        diagnostics["semantic_without_dependencies"][article_id] = {
            "candidate_pair_count": len(semantic_rows),
            "author_dependencies_read": False,
        }

    forecasts: dict[str, dict] = {mode: {} for mode in modes}
    for target_id in sorted(by_id):
        for mode in modes:
            training_rows = {article_id: source_rows[mode][article_id]
                             for article_id in sorted(by_id) if article_id != target_id}
            forecasts[mode][target_id] = forecast_from_rows(
                training_rows, mode=mode, limit=candidate_limit, min_support=min_support)
            forecasts[mode][target_id]["diagnostics_by_source"] = {
                article_id: diagnostics[mode][article_id] for article_id in training_rows}
            forecasts[mode][target_id]["routing_version"] = ROUTING_VERSION

    seeds = list(permuted_seeds or [0])
    require(seeds and len(seeds) == len(set(seeds)) and all(type(seed) is int for seed in seeds),
            "Unique deterministic permutation seeds required")
    permuted = {seed: {} for seed in seeds}
    permuted_diagnostics = {seed: {} for seed in seeds}
    for seed in seeds:
        seed_rows = {}
        for article_id in sorted(by_id):
            seed_rows[article_id], permuted_diagnostics[seed][article_id] = _permuted_author_groups(
                by_id[article_id], seed + int(fingerprint(article_id)[:8], 16),
                normalized_by_source[article_id])
        for target_id in sorted(by_id):
            training_rows = {article_id: seed_rows[article_id]
                             for article_id in sorted(by_id) if article_id != target_id}
            permuted[seed][target_id] = forecast_from_rows(training_rows, mode="permuted_dependencies",
                limit=candidate_limit, min_support=min_support)
            permuted[seed][target_id]["diagnostics_by_source"] = {
                article_id: permuted_diagnostics[seed][article_id] for article_id in training_rows}
            permuted[seed][target_id]["routing_version"] = ROUTING_VERSION

    # Отложенные графы открываются только здесь, после полного формирования прогнозного реестра.
    evaluation = {mode: {} for mode in modes}
    for mode in modes:
        for target_id in sorted(by_id):
            evaluation[mode][target_id] = evaluate(forecasts[mode][target_id], by_id[target_id])
    permuted_evaluation = {seed: {target_id: evaluate(permuted[seed][target_id], by_id[target_id])
                                  for target_id in sorted(by_id)} for seed in seeds}
    return {"version": VERSION, "corpus_size": len(maps), "candidate_limit": candidate_limit,
            "minimum_publication_support": min_support, "patterns_per_source": {
                mode: forecasts[mode] for mode in modes}, "permuted_forecasts": permuted,
            "evaluation": evaluation, "permuted_evaluation": permuted_evaluation,
            "source_diagnostics": diagnostics, "permuted_diagnostics": permuted_diagnostics,
            "normalizer_version": NORMALIZER_VERSION,
            "model_calls": 0, "network_disabled": True, "scientific_claims_forecast": False,
            "confirmatory": False, "sealed_blind_evaluation": False,
            "target_maps_are_known_for_lopo_scoring": True}

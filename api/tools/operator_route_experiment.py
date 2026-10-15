"""Экспериментальные типы операторов; production-словарь не изменяется."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API = ROOT / "api"
if str(API) not in sys.path:
    sys.path.insert(0, str(API))

from domain.article_maps import fingerprint
from domain.comparison_normalization import normalize_map
from domain.development_prediction import validate_visible_dag
from domain.operator_frame_routing import PREDICATES

VERSION = "reviewed-predicate-families-training21-v1"
EXPERIMENTAL_FAMILIES = {
    "reported_incidence": {
        "predicates": [
            "incidence rate", "incident mci rate", "age-specific incidence",
            "age specific mci incidence rate", "adjusted incidence rate",
            "amnestic mci incidence rate", "mci incidence", "reported cohort incidence",
        ],
        "reason_ru": "Сохраняет показатели возникновения случаев отдельно от распространённости; значения, популяции и единицы остаются в исходном знании.",
    },
    "reported_prevalence": {
        "predicates": ["prevalence", "reported cohort prevalence", "subgroup mci prevalence"],
        "reason_ru": "Отдельный тип распространённости; не объединяется с заболеваемостью или частотой новых случаев.",
    },
    "reported_model_parameter": {
        "predicates": ["adjusted hazard ratio"],
        "reason_ru": "Оценка модели отнесена к семейству параметров модели; модель, исход, контраст и число остаются раздельными.",
    },
    "reported_non_detection": {
        "predicates": [
            "association not statistically detected", "difference not statistically detected",
            "not statistically significant in adjusted model",
        ],
        "reason_ru": "Фиксирует отсутствие статистического обнаружения, не доказывая нулевой эффект или эквивалентность.",
    },
    "diagnostic_criterion": {
        "predicates": ["requires absence of dementia"],
        "reason_ru": "Условие операционального диагностического определения; ограничено указанной классификацией и популяцией.",
    },
}

EXPERIMENTAL_PREDICATES = dict(PREDICATES)
for _family, _definition in EXPERIMENTAL_FAMILIES.items():
    for _predicate in _definition["predicates"]:
        EXPERIMENTAL_PREDICATES[_predicate] = _family

MODES = ("coarse", "exact_operator_family", "curated_operator_family", "curated_operator_roles")
MAXIMUM_ARITY = 3


def shape(source_types: list[str], target_type: str) -> dict:
    return {"arity": len(source_types), "source_types": sorted(source_types), "target_type": target_type}


def shape_id(value: dict) -> str:
    return fingerprint(value)


def types_for_map(snapshot: dict) -> dict:
    """Создаёт четыре уровня абстракции, не меняя исходные знания и рёбра."""
    graph = snapshot["graph"]
    validate_visible_dag(graph)
    knowledge = {item["knowledge_id"]: item for item in graph["knowledge"]}
    normalized = {item["id"]: item for item in normalize_map(snapshot)}
    node_to_knowledge = {node["id"]: node["knowledge_id"] for node in graph["nodes"]}
    block_types = {mode: {} for mode in MODES}
    catalogs = {mode: {} for mode in MODES}
    for knowledge_id, item in knowledge.items():
        row = normalized[knowledge_id]
        base = {"kind": item["kind"], "knowledge_kind": item["knowledge_kind"]}
        block_types["coarse"][knowledge_id] = f"{base['kind']}/{base['knowledge_kind']}"
        catalogs["coarse"][block_types["coarse"][knowledge_id]] = base

        for mode, route_table in (("exact_operator_family", PREDICATES),
                                  ("curated_operator_family", EXPERIMENTAL_PREDICATES),
                                  ("curated_operator_roles", EXPERIMENTAL_PREDICATES)):
            operators = sorted({route_table.get(statement["predicate"],
                                                "unregistered:" + statement["predicate"])
                                for statement in row["statements"]})
            family_payload = {**base, "action_status": item["action_status"],
                              "logic": row["logic"], "operator_families": operators}
            payload = family_payload
            if mode == "curated_operator_roles":
                role_shapes = []
                for statement in row["statements"]:
                    scope = statement["scope"]
                    role_shapes.append({
                        "operator_family": EXPERIMENTAL_PREDICATES.get(
                            statement["predicate"], "unregistered:" + statement["predicate"]),
                        "roles": sorted(role["role"] for role in statement["roles"]),
                        "negated": statement["negated"],
                        "quantifier": scope["quantifier"],
                        "modality": scope["modality"],
                        "has_time": scope["time"] is not None,
                        "has_conditions": bool(scope["conditions"]),
                    })
                payload = {**family_payload, "statement_shapes": sorted(role_shapes, key=fingerprint)}
            type_id = mode + ":" + fingerprint(payload)
            block_types[mode][knowledge_id] = type_id
            catalogs[mode][type_id] = payload

    transitions = {mode: [] for mode in MODES}
    for transition in graph["transitions"]:
        source_ids = [node_to_knowledge[node_id] for node_id in transition["sources"]]
        target_id = node_to_knowledge[transition["target"]]
        if len(source_ids) > MAXIMUM_ARITY:
            continue
        for mode in MODES:
            transitions[mode].append(shape(
                [block_types[mode][knowledge_id] for knowledge_id in source_ids],
                block_types[mode][target_id],
            ))
    return {"block_types": block_types, "transitions": transitions, "catalogs": catalogs}


def route_table() -> dict:
    return {
        "version": VERSION,
        "base_routing_version": "explicit-operator-frame-routing-3",
        "experimental_families": EXPERIMENTAL_FAMILIES,
        "predicate_to_family": EXPERIMENTAL_PREDICATES,
        "sha256": fingerprint({"version": VERSION, "families": EXPERIMENTAL_FAMILIES,
                               "predicate_to_family": EXPERIMENTAL_PREDICATES}),
        "interpretation_ru": "Семейство служит только для структурного сопоставления; оно не утверждает эквивалентность разных предикатов или научных фактов.",
    }

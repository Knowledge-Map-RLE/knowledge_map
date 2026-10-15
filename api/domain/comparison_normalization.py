"""Версионируемая нормализация семантики; карты и локальные идентификаторы не меняются."""
from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation

from domain.article_maps import fingerprint, require

VERSION = "schema6-normalizer-4"
AUXILIARY_ATTRIBUTES = frozenset({"source grounded description"})
DICTIONARY = {
    "auxiliary_attributes": sorted(AUXILIARY_ATTRIBUTES),
    "duration_unit_suffixes": {"years": "year", "months": "month", "days": "day", "hours": "hour", "minutes": "minute"},
    "concepts": {
        "mci": "mild cognitive impairment", "ad": "alzheimer disease",
        "alzheimer's disease": "alzheimer disease", "alzheimer’s disease": "alzheimer disease",
        "tnf-α": "tumor necrosis factor alpha", "tnf-alpha": "tumor necrosis factor alpha",
        "tnfa": "tumor necrosis factor alpha", "tumor necrosis factor α": "tumor necrosis factor alpha",
        "il-6": "interleukin 6", "il6": "interleukin 6", "interleukin-6": "interleukin 6",
        "cni": "cognitively non-impaired", "mmse": "mini mental state examination",
        "mini-mental state examination": "mini mental state examination",
        "csf": "cerebrospinal fluid", "bbb": "blood brain barrier",
        "aβ": "amyloid beta", "amyloid β": "amyloid beta",
        "cac": "cretan aging cohort", "psg": "polysomnography",
    },
    "predicates": {
        "is characterized by": "characterized by", "defined by": "characterized by",
        "defined as": "characterized by", "definition": "characterized by",
        "associated with": "associated with", "is associated with": "associated with",
        "correlated with": "correlated with", "is correlated with": "correlated with",
        "measured using": "measured using", "assessed using": "measured using",
        "diagnostic criteria": "diagnostic criteria", "mci diagnostic requirement": "diagnostic criteria",
        "mci progression risk": "dementia conversion", "conversion range": "dementia conversion",
        "conversion estimate": "dementia conversion", "pooled conversion": "dementia conversion",
        "reported mci frequency": "mci incidence", "mci incidence by age": "mci incidence",
        "assessed sleep complaints": "measure subjective sleep", "measure subjective sleep": "measure subjective sleep",
        "recorded lifestyle": "measure physical activity", "measure physical activity": "measure physical activity",
        "measured biomarkers elisa": "measure biomarkers", "measure biomarkers": "measure biomarkers",
    },
    "roles": {"entity": "subject", "agent": "actor"},
    "units": {"%": "percent", "percentage": "percent", "years": "year",
              "months": "month", "pg/ml": "pg/ml", "per 1000 person-years": "per1000personyear",
              "per 1000 person years": "per1000personyear", "/1000 person-years": "per1000personyear",
              "per1000 person-years": "per1000personyear", "per 100 person-years": "per100personyear",
              "minutes": "minute", "hours": "hour", "days": "day", "pg/ml": "pg/ml"},
}
DICTIONARY_SHA256 = fingerprint(DICTIONARY)


def normalize(value):
    return " ".join(unicodedata.normalize("NFKC", str(value)).casefold().replace("_", " ").split())


def canonical(value, category):
    key = normalize(value)
    return DICTIONARY[category].get(key, key)


def normalize_attribute(attribute):
    name, value = normalize(attribute["name"]), attribute["value"]
    unit = canonical(attribute["unit"], "units") if attribute["unit"] is not None else None
    # Единицу можно восстановить только из явно указанного имени поля.
    if unit is None and "percent" in name:
        unit = "percent"
    if unit is None and re.search(r"\b(?:age|duration|followup|follow up|latency)\b", name):
        suffix = name.split()[-1]
        unit = DICTIONARY["duration_unit_suffixes"].get(suffix)
    factors = {"hour": ("minute", Decimal(60)), "year": ("month", Decimal(12)),
               "per100personyear": ("per1000personyear", Decimal(10))}
    try:
        number = Decimal(str(value))
        if number.is_finite():
            if unit in factors:
                unit, factor = factors[unit]
                number *= factor
            value = format(number.normalize(), "f")
    except (InvalidOperation, ValueError):
        # Диапазон и доверительный интервал не подменяются одним числом.
        pass
    return {"name": name, "value": value, "unit": unit}


def semantic_attributes(raw, predicate):
    """Описательная копия текста не является ограничением утверждения."""
    factual = [normalize_attribute(a) for a in raw if normalize(a["name"]) not in AUXILIARY_ATTRIBUTES]
    auxiliary = [dict(a) for a in raw if normalize(a["name"]) in AUXILIARY_ATTRIBUTES]
    # Две явные границы и записанный интервал получают одну форму, без удаления контекста.
    if canonical(predicate, "predicates") == "dementia conversion":
        bounds = {a["name"]: a for a in factual}
        lower, upper = bounds.get("conversion percent min"), bounds.get("conversion percent max")
        if lower and upper and lower["unit"] == upper["unit"] == "percent":
            factual = [a for a in factual if a["name"] not in {lower["name"], upper["name"]}]
            factual.append({"name": "range", "value": {"minimum": lower["value"], "maximum": upper["value"]}, "unit": "percent"})
        for a in factual:
            if a["name"] == "range" and a["unit"] == "percent" and isinstance(a["value"], str):
                match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*[–−-]\s*(\d+(?:\.\d+)?)\s*", a["value"])
                if match:
                    a["value"] = {"minimum": format(Decimal(match[1]).normalize(), "f"),
                                  "maximum": format(Decimal(match[2]).normalize(), "f")}
    return sorted(factual, key=lambda a: (a["name"], fingerprint(a))), auxiliary


def search_tokens(value):
    """Идентификаторы публикаций и номера ссылок не становятся признаками сходства."""
    value = re.sub(r"\b(?:PMC\d+|10\.\d{4,9}/[^\s]+)\b", " ", value, flags=re.I)
    value = re.sub(r"\[(?:\d+[\s,;–-]*)+\]", " ", value)
    value = normalize(value)
    for alias, meaning in sorted(DICTIONARY["concepts"].items(), key=lambda x: -len(x[0])):
        value = re.sub(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", meaning, value)
    stop = {"the", "a", "an", "of", "in", "to", "and", "or", "with", "for", "by", "was", "were", "is", "are"}
    return [t for t in re.findall(r"[\w]+(?:[.-][\w]+)*", value) if t not in stop]


def contains_unresolved_cycle(value):
    if isinstance(value, dict):
        return "cycle" in value or any(contains_unresolved_cycle(v) for v in value.values())
    if isinstance(value, list):
        return any(contains_unresolved_cycle(v) for v in value)
    return False


def normalize_map(result):
    graph = result["graph"]
    require(graph.get("schema_version") == 6, "Article comparison requires schema 6")
    concepts = {c["id"]: canonical(c["display_text"], "concepts") for c in graph["concepts"]}
    knowledge = {k["knowledge_id"]: k for k in graph["knowledge"]}

    def resolve(kid, path=()):
        require(kid in knowledge, "Unknown comparison knowledge reference")
        if kid in path:
            # Цикл обозначается смыслом, а не идентификатором другого документа.
            return {"cycle": sorted({canonical(s["predicate"], "predicates")
                                     for k in path[path.index(kid):] for s in knowledge[k]["semantic_frame"]["statements"]})}
        k = knowledge[kid]
        return {"logic": k["semantic_frame"]["logic"], "statements": [
            {"predicate": canonical(s["predicate"], "predicates"), "negated": s["negated"],
             "roles": sorted([{"role": canonical(r["role"], "roles"),
                               "value": concepts[r["concept_id"]] if r["concept_id"] else resolve(r["knowledge_id"], path + (kid,))}
                              for r in s["roles"]], key=fingerprint),
             "scope": [s["quantifier"], s["modality"], s["temporal_context"], s["conditions"]],
             "attributes": semantic_attributes(s["qualifiers"]["attributes"], s["predicate"])[0]}
            for s in k["semantic_frame"]["statements"]]}

    def statement(s, k):
        roles = [{"role": canonical(r["role"], "roles"),
                  "value": concepts[r["concept_id"]] if r["concept_id"] else resolve(r["knowledge_id"]),
                  "reference_kind": "concept" if r["concept_id"] else "knowledge"} for r in s["roles"]]
        scope = {"quantifier": normalize(s["quantifier"]) if s["quantifier"] is not None else None,
                 "modality": normalize(s["modality"]) if s["modality"] is not None else None,
                 "time": normalize(s["temporal_context"]) if s["temporal_context"] is not None else None,
                 "conditions": sorted(normalize(c) for c in s["conditions"])}
        scoped_group = any(re.search(r"\b(?:study participants|study sample|study cohort|phase [iv]+|cni participants|mci participants|control group|cohort participants)\b",
                                     str(r["value"])) for r in roles)
        if k["knowledge_kind"] != "definition":
            scoped_group = scoped_group or any(
                r["role"] in {"study group", "cohort", "sample", "participants", "participant group", "control group", "patient group"}
                or re.search(r"\b(?:participants|patients|subjects)\b", str(r["value"])) for r in roles)
        scope["study_group"] = result["article_id"] if scoped_group else None
        attributes, auxiliary = semantic_attributes(s["qualifiers"]["attributes"], s["predicate"])
        raw_factual = [a for a in s["qualifiers"]["attributes"] if normalize(a["name"]) not in AUXILIARY_ATTRIBUTES]
        unknown = (k["knowledge_kind"] != "definition" and not scope["time"] and not scope["conditions"])
        unknown = unknown or any(type(a["value"]) in (int, float) and normalize_attribute(a)["unit"] is None
                                 for a in raw_factual)
        # Циклическая ссылка сохраняется, но её усечённая сигнатура не доказывает тождество участников.
        unknown = unknown or any(contains_unresolved_cycle(r["value"]) for r in roles)
        return {"id": s["statement_id"], "predicate": canonical(s["predicate"], "predicates"),
                "roles": sorted(roles, key=fingerprint), "scope": scope, "negated": s["negated"],
                "attributes": attributes, "auxiliary_attributes": auxiliary, "unknown_context": unknown,
                "provenance": s["provenance"]}

    incoming, outgoing = {}, {}
    nodes = {n["id"]: n["knowledge_id"] for n in graph["nodes"]}
    for t in graph["transitions"]:
        target = nodes[t["target"]]
        sources = [nodes[s] for s in t["sources"]]
        incoming.setdefault(target, []).append(sources)
        for src in sources:
            outgoing.setdefault(src, []).append(target)
    def chain_signature(kid, depth=3):
        if depth == 0:
            return []
        return sorted([{"premises": sorted([{"predicates": sorted(canonical(s["predicate"], "predicates")
                            for s in knowledge[p]["semantic_frame"]["statements"]),
                         "upstream": chain_signature(p, depth - 1)} for p in group], key=fingerprint)}
                       for group in incoming.get(kid, [])], key=fingerprint)

    return [{"id": k["knowledge_id"], "article_id": result["article_id"], "run_id": result["run_id"],
             "text": k["display_text"], "kind": k["kind"], "action_status": k["action_status"],
             "logic": k["semantic_frame"]["logic"], "statements": [statement(s, k) for s in k["semantic_frame"]["statements"]],
             "tokens": search_tokens(k["display_text"]), "provenance": k["provenance"],
             "premise_groups": incoming.get(k["knowledge_id"], []), "outcomes": outgoing.get(k["knowledge_id"], []),
             "chain_signature": chain_signature(k["knowledge_id"])}
            for k in graph["knowledge"]]

"""Вычислимая семантика научных утверждений, отдельно от видимого DAG."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json

from domain.article_maps import fingerprint, require
from domain.comparison_normalization import canonical, normalize, normalize_map, normalize_attribute, contains_unresolved_cycle

VERSION = "research-semantics-5"
CONTEXT_FIELDS = {"species", "population", "study", "cohort", "phase", "sample", "stratum", "design", "time", "setting", "specimen", "measure", "conditions"}
PRESENTATIONS = {"own_result", "background", "method", "hypothesis", "review", "unknown"}
CONTEXT_STATUSES = {"known", "not_reported", "not_applicable"}
DIMENSIONLESS_MEASURES = {"p", "p value", "odds ratio", "risk ratio", "hazard ratio", "r", "r2", "correlation coefficient"}


def unknown_measurement_units(measurements):
    unknown = []
    for item in measurements:
        if item["unit"] is not None or item["name"] in DIMENSIONLESS_MEASURES: continue
        try:
            numeric = Decimal(str(item["value"])).is_finite()
        except InvalidOperation:
            numeric = isinstance(item["value"], (dict, list))
        if numeric: unknown.append("unit:" + item["name"])
    return unknown


@dataclass(frozen=True)
class Evidence:
    article_id: str
    run_id: str
    source_sha256: str
    available_on: str
    family: str | None
    presentation: str
    spans: tuple[dict, ...]


@dataclass(frozen=True)
class SemanticClaim:
    claim_id: str
    knowledge_id: str
    predicate: str
    roles: dict
    negated: bool
    quantifier: str | None
    modality: str | None
    context: dict
    measurements: tuple[dict, ...]
    action_status: str | None
    logic: str
    text: str
    evidence: Evidence
    unresolved: bool = False

    @property
    def proposition(self):
        # Область применимости является частью конкретного факта, а не только его источника.
        return {k: getattr(self, k) for k in ("predicate", "roles", "negated", "quantifier", "modality",
                                             "context", "measurements", "action_status", "logic")}

    @property
    def fact_id(self):
        return fingerprint(self.proposition)

    def to_dict(self):
        return {**asdict(self), "fact_id": self.fact_id, "proposition": self.proposition}


def valid_date(value):
    require(isinstance(value, str), "A publication date is required")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        require(False, "Use an exact ISO publication date")
    require(parsed.isoformat() == value, "Use an exact ISO publication date")
    return value


def context_value(value=None, status="known"):
    require(status in CONTEXT_STATUSES, "Unknown context status")
    require((status == "known") == (isinstance(value, str) and bool(value.strip())), "Invalid context value")
    return {"status": status, "value": normalize(value) if status == "known" else None}


def validate_context(context):
    require(isinstance(context, dict) and not set(context) - CONTEXT_FIELDS, "Unknown scientific context field")
    for item in context.values():
        require(isinstance(item, dict) and set(item) == {"status", "value"}, "Invalid context record")
        require(item == context_value(item["value"], item["status"]), "Context must be canonical")


def source_span(source, start, end, quote=None):
    # Python использует Unicode code points; библиография не является свидетельством извлечения.
    require(type(start) is int and type(end) is int and 0 <= start < end <= source["content_end"], "Invalid scientific source span")
    text = source["text"][start:end]
    require(quote is None or quote == text, "Source quotation differs")
    return {"start": start, "end": end, "text": text, "offset_encoding": "unicode_code_points"}


def verify_map(result):
    source = result["source"]
    require(result["graph"].get("schema_version") == 6, "Research semantics requires schema 6")
    require(sha256(source["text"].encode("utf-8")).hexdigest() == source["sha256"], "Source hash differs")
    require(type(source["content_end"]) is int and 0 < source["content_end"] <= len(source["text"]), "Invalid source content boundary")
    from domain.development_prediction import validate_visible_dag
    validate_visible_dag(result["graph"])


def project_map(result, registry, annotation=None):
    """Готовая карта → представление для анализа; извлечение и модельные клиенты не запускаются."""
    verify_map(result)
    require(registry["article_id"] == result["article_id"] and registry["run_id"] == result["run_id"], "Registry run differs")
    require(registry["source_sha256"] == result["source"]["sha256"], "Registry source differs")
    available = valid_date(registry["available_on"])
    presentation = registry.get("presentation", "unknown")
    require(presentation in PRESENTATIONS, "Unknown evidence presentation")
    source = result["source"]
    units = {u["id"]: u for u in source["units"]}
    normalized = normalize_map(result)
    originals = {s["statement_id"]: s for k in result["graph"]["knowledge"] for s in k["semantic_frame"]["statements"]}
    claims = []
    for knowledge in normalized:
        for statement in knowledge["statements"]:
            scope = statement["scope"]
            context = {"time": context_value(scope["time"], "known" if scope["time"] else "not_reported")}
            if scope["conditions"]:
                context["conditions"] = context_value("; ".join(scope["conditions"]))
            if scope["study_group"]:
                context["study"] = context_value(None, "not_reported")
            if knowledge["kind"] == "state" and not scope["time"] and knowledge["logic"] == "single":
                original = next(k for k in result["graph"]["knowledge"] if k["knowledge_id"] == knowledge["id"])
                if original["knowledge_kind"] == "definition":
                    context["time"] = context_value(None, "not_applicable")
            metadata_fields = {"species": "species", "population": "population", "study id": "study", "cohort id": "cohort",
                               "sample id": "sample", "phase": "phase", "study design": "design", "event time": "time",
                               "setting": "setting", "specimen": "specimen", "measure": "measure", "stratum": "stratum", "conditions": "conditions"}
            metadata = {}
            for attribute in originals[statement["id"]]["qualifiers"]["attributes"]:
                key = normalize(attribute["name"])
                if key in metadata_fields and attribute["value"] is not None:
                    context[metadata_fields[key]] = context_value(str(attribute["value"]))
                    metadata[key] = attribute["value"]
                elif key.startswith("context status "):
                    field = key.removeprefix("context status ")
                    require(field in CONTEXT_FIELDS, "Unknown declared context status field")
                    require(attribute["value"] in {"not_reported", "not_applicable"}, "Invalid declared context status")
                    context[field] = context_value(None, attribute["value"])
                    metadata[key] = attribute["value"]
                elif key in {"evidence presentation", "evidence family"}:
                    metadata[key] = attribute["value"]
            roles = {}
            unresolved = False
            for role in statement["roles"]:
                key = role["role"]
                value = role["value"]
                if key in roles:
                    unresolved = True
                if isinstance(value, dict):
                    # Роли и границы вложенных утверждений сохраняются; цикл не объявляется тождеством.
                    unresolved = unresolved or contains_unresolved_cycle(value)
                    value = {"kind": "knowledge", "structure": value}
                roles[key] = value
            spans = tuple(source_span(source, units[u]["start"], min(units[u]["end"], source["content_end"]))
                          for u in statement["provenance"]["unit_ids"] if units[u]["start"] < source["content_end"])
            require(bool(spans), "Claim has no scientific source evidence")
            evidence = Evidence(result["article_id"], result["run_id"], source["sha256"], available,
                                registry.get("family"),
                                metadata.get("evidence presentation", presentation), spans)
            require(evidence.presentation in PRESENTATIONS, "Invalid source evidence presentation")
            measurements = tuple(a for a in statement["attributes"] if normalize(a["name"]) not in metadata)
            unresolved = unresolved or len({a["name"] for a in measurements}) != len(measurements)
            claims.append(SemanticClaim(statement["id"], knowledge["id"], statement["predicate"], roles,
                statement["negated"], scope["quantifier"], scope["modality"], context,
                measurements, knowledge["action_status"], knowledge["logic"], knowledge["text"], evidence, unresolved))
    if annotation:
        require(annotation["run_id"] == result["run_id"] and annotation["source_sha256"] == source["sha256"]
                and annotation["graph_sha256"] == fingerprint(result["graph"]), "Semantic annotation binding differs")
        known = {c.claim_id for c in claims}
        replacement = set(annotation.get("replaces", []))
        require(replacement <= known, "Unknown replaced statement")
        claims = [c for c in claims if c.claim_id not in replacement]
        knowledge_ids = {k["knowledge_id"] for k in result["graph"]["knowledge"]}
        for raw in annotation.get("claims", []):
            require(raw["knowledge_id"] in knowledge_ids, "Unknown annotated knowledge")
            validate_context(raw["context"])
            spans = tuple(source_span(source, s["start"], s["end"], s["text"]) for s in raw["spans"])
            require(bool(spans), "Annotation has no evidence")
            parent = next(k for k in result["graph"]["knowledge"] if k["knowledge_id"] == raw["knowledge_id"])
            parents = [units[u] for u in parent["provenance"]["unit_ids"]]
            require(all(any(s["start"] < u["end"] and s["end"] > u["start"] for u in parents) for s in spans),
                    "Annotation evidence is unrelated to its parent knowledge")
            evidence = Evidence(result["article_id"], result["run_id"], source["sha256"], available,
                registry.get("family"), raw.get("presentation", presentation), spans)
            require(raw.get("family", registry.get("family")) == registry.get("family"), "Annotated independence family is not verified in registry")
            require(evidence.presentation in PRESENTATIONS, "Unknown annotated presentation")
            roles = {canonical(r, "roles"): canonical(v, "concepts") for r, v in raw["roles"].items()}
            require(bool(roles) and type(raw["negated"]) is bool, "Invalid annotated roles or negation")
            require(raw.get("logic", "single") in {"single", "conjunction", "contrast", "argument", "partition"}, "Unknown frame logic")
            require(raw.get("action_status") in {None, "performed", "planned", "prescribed", "unresolved"}, "Unknown action status")
            claims.append(SemanticClaim(raw["claim_id"], raw["knowledge_id"], canonical(raw["predicate"], "predicates"), roles,
                raw["negated"], raw.get("quantifier"), raw.get("modality"), raw["context"],
                tuple(normalize_attribute(a) for a in raw.get("measurements", [])), raw.get("action_status"),
                raw.get("logic", "single"), raw["text"], evidence))
    require(len({c.claim_id for c in claims}) == len(claims), "Duplicate semantic claim id")
    return claims


def context_difference(left, right):
    conflicts, unknown = [], []
    for key in sorted(set(left) | set(right)):
        a = left.get(key, context_value(None, "not_reported"))
        b = right.get(key, context_value(None, "not_reported"))
        if a["status"] == "not_reported" or b["status"] == "not_reported":
            unknown.append(key)
        elif a != b:
            conflicts.append(key)
    return conflicts, unknown


def compare_claims(left, right):
    """Эквивалентность факта не подменяется сходством шаблона или совпадением числа."""
    result = {"relation": "unrelated", "matched": [], "differences": [], "unknown": []}
    if left.predicate != right.predicate:
        result["differences"] = ["predicate"]
        return result
    common = {k for k in left.roles.keys() & right.roles.keys() if left.roles[k] == right.roles[k]}
    if not common:
        return {**result, "relation": "common_template", "differences": ["participants"]}
    result["matched"] = ["predicate", *sorted(common)]
    conflicts, unknown = context_difference(left.context, right.context)
    unknown += sorted(set(unknown_measurement_units(left.measurements) + unknown_measurement_units(right.measurements)))
    result["unknown"] = unknown
    if conflicts:
        return {**result, "relation": "context_mismatch", "differences": conflicts}
    exact_roles = left.roles == right.roles
    for key in ("quantifier", "modality", "action_status", "logic"):
        if getattr(left, key) != getattr(right, key):
            result["differences"].append(key)
    a = {m["name"]: m for m in left.measurements}
    b = {m["name"]: m for m in right.measurements}
    # Порядок диагностических полей входит в неизменяемые артефакты.
    # Перебор множества зависел от случайного hash seed процесса.
    for key in sorted(a.keys() & b.keys()):
        if a[key]["unit"] != b[key]["unit"]:
            result["differences"].append("unit:" + key)
        elif a[key] != b[key]:
            result["differences"].append("value:" + key)
        else:
            result["matched"].append("measurement:" + key)
    if any(d.startswith("unit:") for d in result["differences"]):
        return {**result, "relation": "unit_mismatch"}
    if left.negated != right.negated:
        relation = "contradiction" if exact_roles and a == b and not result["differences"] and not unknown and not (left.unresolved or right.unresolved) else "polarity_difference"
        return {**result, "relation": relation}
    if exact_roles and a == b and not result["differences"] and not unknown and not (left.unresolved or right.unresolved):
        return {**result, "relation": "equivalent"}
    if not exact_roles:
        result["differences"].append("participants")
    if a != b and not result["differences"]:
        result["differences"].append("measurements")
    return {**result, "relation": "partial" if exact_roles or len(common) >= 2 else "common_template"}


def semantic_audit(maps, registry, annotations, controls):
    from domain.research_diagnostics import VERSION as DIAGNOSTIC_VERSION, coverage_detail, eligibility_summary
    require(len({m["article_id"] for m in maps}) == len(maps), "Duplicate audit article")
    projected, native = {}, {}
    for m in maps:
        key = m["article_id"]
        require(key in registry, "Scientific metadata missing")
        native[key] = project_map(m, registry[key])
        projected[key] = project_map(m, registry[key], annotations.get(key))
    rows = []
    for pair in controls["pairs"]:
        ends = []
        for endpoint in ("left", "right"):
            ref = pair[endpoint]
            require(ref["article_id"] in projected, "Unknown control article")
            found = [c for c in projected[ref["article_id"]] if c.claim_id in ref["claim_ids"]]
            require(len(found) == len(ref["claim_ids"]), "Unknown control claim")
            ends.append(found)
        comparisons = [{"left": a.claim_id, "right": b.claim_id, **compare_claims(a, b)} for a in ends[0] for b in ends[1]]
        relations = {c["relation"] for c in comparisons}
        passed = all(r in relations for r in pair["expected_relations"])
        # Покрытие готовой карты проверяется отдельно от добавленных контрольных атомов.
        native_presence = []
        native_details = []
        for endpoint, found in zip(("left", "right"), ends):
            article = pair[endpoint]["article_id"]
            native_presence.append(all(any(compare_claims(a, b)["relation"] == "equivalent" for b in native[article]) for a in found))
            native_details.append([coverage_detail(a, native[article]) for a in found])
        rows.append({"id": pair["id"], "passed": passed, "expected_relations": pair["expected_relations"],
                     "native_fully_represented": native_presence, "native_details": native_details,
                     "comparisons": comparisons, "note_ru": pair["note_ru"]})
    return {"version": VERSION, "source_count": len(maps), "native_claim_count": sum(map(len, native.values())),
            "analytic_claim_count": sum(map(len, projected.values())), "controls_passed": sum(r["passed"] for r in rows),
            "control_count": len(rows), "controls": rows, "maps": [{"article_id": m["article_id"], "run_id": m["run_id"],
                "graph_sha256": fingerprint(m["graph"]), "source_sha256": m["source"]["sha256"]} for m in maps],
            "annotations_sha256": fingerprint(annotations), "controls_sha256": fingerprint(controls),
            "claims": {a: [c.to_dict() for c in cs] for a, cs in projected.items()},
            "diagnostic_version": DIAGNOSTIC_VERSION,
            "eligibility": {"native": eligibility_summary(c for cs in native.values() for c in cs),
                            "analytic": eligibility_summary(c for cs in projected.values() for c in cs)},
            "native_control_endpoint_count": sum(len(r["native_fully_represented"]) for r in rows),
            "native_control_endpoints_represented": sum(sum(r["native_fully_represented"]) for r in rows),
            "author": "Codex", "expert_validated": False, "model_calls": 0}

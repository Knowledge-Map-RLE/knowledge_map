"""Проверяемая ручная ревизия контекста; исходная карта остаётся неизменной."""
from copy import deepcopy
from datetime import date

from domain.article_maps import digest, fingerprint, require
from domain.research_semantics import validate_context

VERSION = "research-context-revision-1"


def apply_context_revision(bundle, audit):
    """Проверка происхождения не заменяет экспертную проверку интерпретации Codex."""
    require(set(audit) == {"version", "scope", "author", "expert_validated", "sources", "tables", "patches"}, "Context audit fields differ")
    require(audit["version"] == VERSION and audit["scope"] in {"primary", "sensitivity"}, "Unknown context audit version or scope")
    require(audit["author"] == "Codex" and audit["expert_validated"] is False, "Manual scientific review attribution required")
    result, original = bundle["map"], bundle["annotation"]
    require(original["run_id"] == result["run_id"] and original["source_sha256"] == result["source"]["sha256"]
            and original["graph_sha256"] == fingerprint(result["graph"]), "Original annotation binding differs")
    own = result["article_id"]
    sources = {own: {"text": result["source"]["text"], "sha256": result["source"]["sha256"], "kind": "training_full_text"}}
    for source in audit["sources"]:
        require(set(source) == {"id", "text", "sha256", "kind", "available_on", "url", "training"}, "Supporting context source fields differ")
        require(source["id"] not in sources and source["kind"] == "primary_methods_abstract" and source["training"] is False,
                "Supporting abstract cannot become a training article")
        require(digest(source["text"]) == source["sha256"], "Supporting context source hash differs")
        require(date.fromisoformat(source["available_on"]) <= date.fromisoformat(bundle["registry"]["available_on"]), "Context source is later than original publication")
        require(source["url"].startswith("https://"), "Primary context source URL required")
        sources[source["id"]] = source
    tables = {t["id"]: t for t in audit["tables"]}
    require(len(tables) == len(audit["tables"]), "Duplicate context table")
    for table in tables.values():
        require(set(table) == {"id", "local_path", "sha256", "bbox", "transcription", "note_ru"}, "Table evidence fields differ")
        require(len(table["sha256"]) == 64 and bool(table["transcription"]) and bool(table["note_ru"]), "Manual table transcription required")
        box = table["bbox"]
        require(len(box) == 4 and all(type(v) is int and v >= 0 for v in box) and box[0] < box[2] and box[1] < box[3], "Invalid source table region")
    annotation = deepcopy(original)
    claims = {c["claim_id"]: c for c in annotation["claims"]}
    require(len({p["claim_id"] for p in audit["patches"]}) == len(audit["patches"]), "Duplicate context patch")
    for patch in audit["patches"]:
        require(set(patch) == {"claim_id", "original_claim_sha256", "quality", "context", "measurements_append", "evidence", "table_ids", "rationale_ru"}, "Context patch fields differ")
        require(patch["claim_id"] in claims, "Unknown context claim")
        claim = claims[patch["claim_id"]]
        require(fingerprint(claim) == patch["original_claim_sha256"], "Original context claim changed")
        require(patch["quality"] in {"operational_screen_with_explicit_cohort_link", "author_reported_nondemented"}, "Unknown context evidence quality")
        require(patch["quality"] != "author_reported_nondemented" or audit["scope"] == "sensitivity", "Author-reported nondementia is sensitivity only")
        require(set(patch["context"]) <= {"population", "stratum"} and bool(patch["rationale_ru"]), "Only explicit population and stratum refinements allowed")
        validate_context({**claim["context"], **patch["context"]})
        evidence_sources = set()
        require(bool(patch["evidence"]), "Context patch needs exact evidence")
        for span in patch["evidence"]:
            require(set(span) == {"source_id", "sha256", "start", "end", "text", "offset_encoding"}, "Context evidence fields differ")
            require(span["source_id"] in sources, "Unknown context source")
            source = sources[span["source_id"]]
            require(span["sha256"] == source["sha256"] and span["offset_encoding"] == "unicode_code_points", "Context evidence binding differs")
            require(type(span["start"]) is int and type(span["end"]) is int and 0 <= span["start"] < span["end"] <= len(source["text"])
                    and source["text"][span["start"]:span["end"]] == span["text"], "Context evidence span differs")
            evidence_sources.add(span["source_id"])
        require(own in evidence_sources, "Own article evidence required for context revision")
        if patch["quality"] == "operational_screen_with_explicit_cohort_link":
            require(bool(evidence_sources - {own}), "Explicit primary cohort link required")
        require(set(patch["table_ids"]) <= tables.keys(), "Unknown source table")
        measurements = patch["measurements_append"]
        require(not measurements or bool(patch["table_ids"]) or any(s["source_id"] == own and "|" in s["text"] for s in patch["evidence"]),
                "Additional measurements require archived table evidence")
        require(all(set(m) == {"name", "value", "unit"} for m in measurements), "Context measurement fields differ")
        names = [m["name"] for m in [*claim.get("measurements", []), *measurements]]
        require(len(names) == len(set(names)), "Duplicate context measurement")
        claim["context"].update(deepcopy(patch["context"]))
        claim["measurements"] = [*claim.get("measurements", []), *deepcopy(measurements)]
    annotation["context_revision"] = {"version": VERSION, "scope": audit["scope"], "audit_sha256": fingerprint(audit),
                                      "original_annotation_sha256": fingerprint(original), "expert_validated": False}
    return annotation

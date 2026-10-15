"""Проверка адресной разметки Codex без генератора знаний и AI-клиентов."""
from domain.article_maps import digest, fingerprint, require
from domain.primary_evidence import VERSION, audit_measurement, independent_cohorts, verify_fragment


def validate_primary_qualification(annotation, source_records, source_texts):
    require(annotation["author"] == "Codex" and annotation["expert_validated"] is False, "Annotation authorship missing")
    require(annotation["model_calls"] == 0 and annotation["predictions"] == [], "Source audit must not contain generated predictions")
    allowed = {r["entry"]["id"]: r for r in source_records if r["status"] == "training_fulltext_saved"}
    require(set(source_texts) == set(allowed) == set(annotation["sources"]), "Explicit primary corpus differs")
    for key, record in allowed.items():
        require(record["source_sha256"] == digest(source_texts[key]), "Source revision differs from audit")
        require(record["metadata"]["pmcid"] == annotation["sources"][key]["pmcid"], "Primary identity differs")
    evidence = annotation["evidence"]
    for key, proof in evidence.items():
        require(key == proof["id"] and proof["source_id"] in allowed, "Unknown primary evidence reference")
        text = source_texts[proof["source_id"]]
        verify_fragment(proof, text)
        references = text.find("## References")
        require(references >= 0 and proof["end"] <= references, "Bibliography cannot be primary result evidence")
    measurements, ids = [], set()
    for observation in annotation["measurements"]:
        require(observation["id"] not in ids, "Duplicate measurement identifier")
        ids.add(observation["id"])
        source = annotation["sources"][observation["source_id"]]
        require(observation["context"]["cohort_id"] == source["cohort_id"], "Measurement cohort binding differs")
        require(bool(observation["evidence_ids"]), "Measurement must cite primary evidence")
        for key in observation["evidence_ids"]:
            require(key in evidence and evidence[key]["source_id"] == observation["source_id"], "Cross-source measurement evidence")
        measurements.append(audit_measurement(observation))
    for source_id, source in annotation["sources"].items():
        require(source["evidence_ids"] and all(key in evidence and evidence[key]["source_id"] == source_id
                                              for key in source["evidence_ids"]), "Source qualification evidence missing")
    for issue in annotation["diagnostics"]:
        require(issue["evidence_ids"] and all(key in evidence for key in issue["evidence_ids"]), "Diagnostic evidence missing")
    return {"version": VERSION, "annotation_sha256": fingerprint(annotation), "measurements": measurements,
            "verified_sources": len(allowed), "verified_fragments": len(evidence),
            "cohort_groups": independent_cohorts([o["context"] for o in annotation["measurements"]]),
            "quarantined_measurements": sum(r["status"] == "quarantined" for r in measurements),
            "scientific_success": False, "new_predictions": 0, "model_calls": 0,
            "qualification": "Codex annotations require expert review; numeric consistency is not scientific validity"}

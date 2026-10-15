"""Проверка зафиксированных гипотез без подмены отсутствующих результатов."""
from collections import Counter
from datetime import date

from domain.article_maps import require
from domain.qualitative_relations import signature, validate_claim

VERSION = "frozen-transfer-control-2"
MODES = {"semantic", "known_union", "frequency"}


def audit_control(frozen, control):
    generation = frozen["generation"]
    modes = generation["forecast"]["predictions"]
    require(set(modes) == MODES, "Frozen baseline modes differ")
    require(control["forecast_run_id"] == frozen["run_id"], "Control bound to another forecast")
    require(control["model_calls"] == 0 and control["expert_validated"] is False and control["author"] == "Codex", "Unexpected control annotation status")
    try:
        parsed_date = date.fromisoformat(control["publication_date"])
    except (ValueError, TypeError):
        require(False, "Exact ISO publication date required")
    require(parsed_date.isoformat() == control["publication_date"], "Exact ISO publication date required")
    families = control["cohort_ids"]
    require(families and len(set(families)) == len(families), "Control cohort identity missing")
    require(not set(families) & set(generation["training_families"]), "Training cohort reused as independent control")
    require(control["publication_date"] > frozen["inputs"]["protocol"]["training_cutoff"], "Control precedes training cutoff")
    require(frozen["inputs"]["protocol"]["selection"]["publication_from"] <= control["publication_date"] <=
            frozen["inputs"]["protocol"]["selection"]["publication_until"], "Control outside frozen publication window")
    require(isinstance(control["observations"], list), "Explicit observations required")
    require(len({c["id"] for c in control["observations"]}) == len(control["observations"]), "Duplicate control observation")
    for claim in control["observations"]:
        validate_claim(claim)
        require(claim["family_id"] in families and claim["source_id"] == control["source_id"], "Control provenance differs")
    results = {}
    hard = control["hard_context"]
    require(set(hard) == {"general_older_adults", "baseline_free_of_mci_and_dementia", "prospective_incidence"}, "Hard context fields differ")
    require(all(value is None or type(value) is bool for value in hard.values()), "Hard context must be explicit or unknown")
    for mode, candidates in modes.items():
        rows = []
        for candidate in candidates:
            sig = candidate["signature"]
            observations = [c for c in control["observations"] if dict(zip(
                ("factor", "contrast", "phenotype", "estimand"), signature(c))) == sig]
            other_directions = {c["expected_direction"] for c in candidates if c["signature"] == sig}
            reporting = next((r for r in control["reporting"] if r["factor"] == sig["factor"] and
                              r["phenotype"] == sig["phenotype"] and r["estimand"] == sig["estimand"]), None)
            blockers = [k for k, value in hard.items() if value is not True]
            if not control["full_source_review"]:
                blockers.append("incomplete_source_review")
            comparisons = []
            for observation in observations:
                observation_blockers = list(blockers)
                critical = observation["context"]["critical"]
                if critical.get("baseline_status") != "no_mci_no_dementia":
                    observation_blockers.append("observation_baseline_status")
                if critical.get("population") != "general_older_adults":
                    observation_blockers.append("observation_population")
                if critical.get("phenotype") != observation["phenotype"]:
                    observation_blockers.append("observation_phenotype")
                # Нельзя объявить HR, сохранив под ним единицы частоты или OR.
                if sig["estimand"] == "hazard_association" and (
                    critical.get("measure") != "hazard_ratio" or critical.get("unit") != "dimensionless"
                ):
                    observation_blockers.append("hazard_measurement_metadata")
                result = observation["result"]
                direction = result["direction"]
                agreement = direction == candidate["expected_direction"] if direction in {"higher", "lower", "equal"} else None
                if observation_blockers:
                    status = "unassessable"
                elif len(other_directions) > 1:
                    status = "ambiguous_baseline"
                elif result["statistical_finding"] != "detected" or agreement is None:
                    status = "uncertain"
                elif agreement:
                    status = "qualitative_pattern_match"
                else:
                    status = "inconsistent_transfer"
                comparisons.append({"observation_id": observation["id"], "status": status,
                                    "blockers": observation_blockers,
                                    "direction_agreement": agreement, "observed_result": result,
                                    "control_context": observation["context"], "provenance": observation["provenance"]})
            if comparisons:
                statuses = {c["status"] for c in comparisons}
                status = next(iter(statuses)) if len(statuses) == 1 else "conflicting_control_results"
            elif blockers:
                status = "unassessable"
            else:
                status = "not_addressed"
            differences = [{"observation_id": c["id"], "different_fields": [k for k in sig if c[k] != sig[k]]}
                           for c in control["observations"] if c["factor"] == sig["factor"] and c not in observations]
            rows.append({"candidate_id": candidate["id"], "signature": sig,
                         "expected_direction": candidate["expected_direction"], "status": status,
                         "comparisons": comparisons, "incompatible_observations": differences,
                         "blockers": blockers, "reporting": reporting,
                         "support_cohorts": candidate["cohorts"], "premise_ids": candidate["premise_ids"],
                         "scientific_fact_equivalence": False, "causality_confirmed": False})
        counts = dict(Counter(row["status"] for row in rows))
        decisive = counts.get("qualitative_pattern_match", 0) + counts.get("inconsistent_transfer", 0)
        results[mode] = {"rows": rows, "counts": counts, "candidate_count": len(candidates),
                         "compatible_reported_candidates": sum(bool(row["comparisons"]) for row in rows),
                         "decisive_candidates": decisive,
                         "direction_accuracy": counts.get("qualitative_pattern_match", 0) / decisive if decisive else None}
    semantic = results["semantic"]
    return {"version": VERSION, "modes": results, "source_audit_performed": True,
            "empirical_test_performed": semantic["decisive_candidates"] > 0,
            "independent_pattern_matches": semantic["counts"].get("qualitative_pattern_match", 0),
            "decisive_semantic_candidates": semantic["decisive_candidates"],
            "graph_gain": None, "graph_advantage_demonstrated": False,
            "scientific_success": False, "expert_validated": False,
            "evaluation_design": "historical holdout after forecast seal; not pre-publication prediction",
            "context_limits": control["context_limits"]}

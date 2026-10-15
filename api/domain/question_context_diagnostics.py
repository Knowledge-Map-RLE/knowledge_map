"""Матрица различий допустимых наблюдений не является предиктором."""
from collections import Counter
from itertools import combinations

from domain.article_maps import require
from domain.qualitative_question_prediction import IDENTITY

VERSION = "question-context-diagnostics-1"


def diagnose_context(forecast):
    rows = sorted((r for r in forecast["observations"] if r["projected"]), key=lambda r: r["reference"])
    require(len({tuple(r["reference"]) for r in rows}) == len(rows), "Duplicate diagnostic observation")
    pairs, differences = [], Counter()
    for a, b in combinations(rows, 2):
        ea, eb = a["original"]["evidence"], b["original"]["evidence"]
        if ea["family"] == eb["family"]:
            continue
        pa, pb = a["projected"]["proposition"], b["projected"]["proposition"]
        details = []
        for name in sorted((pa["context"].keys() | pb["context"].keys()) - IDENTITY):
            left, right = pa["context"].get(name), pb["context"].get(name)
            if left != right: details.append({"field": "context:" + name, "left": left, "right": right})
        ma, mb = ({m["name"]: m for m in p["measurements"]} for p in (pa, pb))
        for name in sorted(ma.keys() | mb.keys()):
            if ma.get(name) != mb.get(name): details.append({"field": "constraint:" + name, "left": ma.get(name), "right": mb.get(name)})
        for name in ("predicate", "roles", "negated", "quantifier", "action_status", "logic"):
            if pa[name] != pb[name]: details.append({"field": name, "left": pa[name], "right": pb[name]})
        differences.update(d["field"] for d in details)
        pairs.append({"left": a["reference"], "right": b["reference"], "families": [ea["family"], eb["family"]],
                      "available_on": [ea["available_on"], eb["available_on"]], "differences": details,
                      "findings": [pa["modality"], pb["modality"]], "same_finding_label": pa["modality"] == pb["modality"],
                      "status": "unsupported_transfer_under_current_contract" if details else "applicability_equal_under_current_contract"})
    return {"version": VERSION, "forecast_run_id": forecast["run_id"], "accepted_observations": len(rows), "cross_family_pairs": len(pairs),
            "applicability_equal_pairs": sum(not p["differences"] for p in pairs), "difference_counts": dict(sorted(differences.items())),
            "pairs": pairs, "status": "contract_diagnostic_not_forecast_or_scientific_incompatibility_proof", "model_calls": 0}

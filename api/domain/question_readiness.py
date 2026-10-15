"""Порог готовности реального корпуса перед чтением независимой цели."""
from domain.question_prediction import eligible, question_matches

VERSION = "question-readiness-1"


def assess_readiness(forecast, claims, source_count):
    claims = list(claims)
    from domain.question_prediction import ForecastQuestion
    question = ForecastQuestion.parse(forecast["question"])
    empirical = [c for c in claims if eligible(c) and c.evidence.presentation == "own_result"
                 and c.evidence.family and question_matches(c.proposition, question)]
    families = sorted({c.evidence.family for c in empirical})
    checks = {
        "five_full_text_sources": source_count >= 5,
        "two_question_relevant_independent_families": len(families) >= 2,
        "historical_learning_present": bool(forecast["rules"]["semantic"]),
        "question_forecast_present": bool(forecast["modes"]["semantic"]),
    }
    return {"version": VERSION, "status": "ready_for_independent_target" if all(checks.values()) else "needs_corpus_revision",
            "checks": checks, "failed_checks": [k for k, v in checks.items() if not v],
            "source_count": source_count, "question_relevant_own_claims": len(empirical),
            "independent_families": families, "dependency_learning_present": bool(forecast["rules"]["dependency"]),
            "target_reading_allowed": all(checks.values()), "expert_validated": False}

"""Проверки измерений первичного источника, отдельные от генерации прогнозов."""
from decimal import Decimal, InvalidOperation

from domain.article_maps import digest, require

VERSION = "primary-evidence-audit-1"
RATE_UNITS = {"per_100_person_years": Decimal(100), "per_1000_person_years": Decimal(1000)}


def number(value):
    require(isinstance(value, str), "Measurements must preserve published decimal strings")
    try:
        result = Decimal(value)
    except InvalidOperation:
        require(False, "Invalid published number")
    require(result.is_finite(), "Non-finite published number")
    return result


def verify_fragment(proof, source):
    require(proof["offset_encoding"] == "unicode_codepoints", "Unknown source coordinate encoding")
    require(proof["source_sha256"] == digest(source), "Primary source revision differs")
    start, end = proof["start"], proof["end"]
    require(type(start) is int and type(end) is int and 0 <= start < end <= len(source), "Invalid source coordinates")
    require(source[start:end] == proof["text"], "Primary fragment differs")
    require(digest(proof["text"]) == proof["text_sha256"], "Primary fragment hash differs")


def audit_measurement(observation):
    """Несогласованный опубликованный результат остаётся в аудите, но попадает в карантин."""
    value = number(observation["value"])
    require(value >= 0, "Negative rate or ratio")
    unit = observation["unit"]
    require(unit in {*RATE_UNITS, "hazard_ratio"}, "Unknown measurement dimension")
    issues, warnings = [], []
    interval = observation["confidence_interval"]
    if interval is None:
        warnings.append("confidence_interval_not_reported")
    else:
        require(len(interval) == 2, "Two interval bounds required")
        lower, upper = map(number, interval)
        require(0 <= lower <= upper, "Invalid confidence bounds")
        if not lower <= value <= upper:
            issues.append("point_outside_published_confidence_interval")
    denominator = observation.get("denominator")
    if denominator is not None:
        require(unit in RATE_UNITS, "A ratio must not receive a rate denominator")
        count, years = number(observation["events"]), number(denominator["person_years"])
        require(count >= 0 and count == count.to_integral_value() and years > 0, "Invalid event count or person time")
        if denominator["role"] != "population_at_risk_time":
            issues.append("denominator_is_not_population_at_risk_time")
        else:
            calculated = count / years * RATE_UNITS[unit]
            half_last_digit = Decimal(5).scaleb(value.as_tuple().exponent - 1)
            if abs(calculated - value) > half_last_digit:
                issues.append("rate_not_reproduced_at_published_precision")
    normalized = value * Decimal(1000) / RATE_UNITS[unit] if unit in RATE_UNITS else None
    return {"id": observation["id"], "issues": issues, "warnings": warnings,
            "status": "quarantined" if issues else "numerically_consistent",
            "value_per_1000_person_years": str(normalized) if normalized is not None else None,
            "scientific_validation": False}


def transfer_barriers(left, right):
    """Контекст должен совпасть явно; отсутствие информации не доказывает совместимость."""
    reasons = []
    for key in ("population", "endpoint_definition", "baseline_riskset", "sex", "age_band", "adjustment"):
        a, b = left.get(key), right.get(key)
        if a is None or b is None:
            reasons.append("unknown:" + key)
        elif a != b:
            reasons.append("different:" + key)
    return reasons


def independent_cohorts(observations):
    require(all(o.get("cohort_id") for o in observations), "Independent support requires identified cohorts")
    return sorted({o["cohort_id"] for o in observations})

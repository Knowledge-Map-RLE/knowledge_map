"""Выводит статистическую квалификацию из наблюдённых данных, не прогнозируя новый эффект."""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from domain.article_maps import require

VERSION = 'statistical-evidence-derivation-1'


@dataclass(frozen=True)
class StatisticalEvidence:
    effect: str
    unit: str
    estimate: float
    ci95: tuple[float, float] | None
    p: float | None
    higher_means_more_decline: bool


def number(value):
    require(not isinstance(value, bool), 'Boolean is not a statistical estimate')
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        require(False, 'Finite statistical value required')
    require(result.is_finite(), 'Finite statistical value required')
    return result


def derive_evidence_label(evidence: StatisticalEvidence, alpha=0.05):
    """Согласие p и CI проверяется без подмены единиц, причинности или исхода."""
    require(evidence.effect in {'odds_ratio','linear_coefficient'}, 'Unsupported effect; no automatic conversion')
    require(type(evidence.higher_means_more_decline) is bool, 'Explicit outcome orientation required')
    estimate = number(evidence.estimate); threshold = number(alpha)
    require(0 < threshold < 1, 'Alpha must be between zero and one')
    if evidence.effect == 'odds_ratio':
        require(evidence.unit == 'dimensionless' and estimate > 0, 'Odds ratio must be positive and dimensionless')
        null = Decimal(1)
    else:
        require(bool(evidence.unit) and evidence.unit != 'dimensionless', 'Explicit coefficient outcome unit required')
        null = Decimal(0)
    p = None if evidence.p is None else number(evidence.p)
    require(p is None or 0 <= p <= 1, 'P-value must be between zero and one')
    interval = None
    if evidence.ci95 is not None:
        require(len(evidence.ci95) == 2, 'Two confidence bounds required')
        interval = tuple(number(v) for v in evidence.ci95)
        require(interval[0] <= estimate <= interval[1], 'Confidence interval must contain its estimate')
        if evidence.effect == 'odds_ratio':
            require(interval[0] > 0, 'Odds-ratio confidence interval must be positive')
    base = {'version':VERSION,'alpha':float(threshold),'null_reference':float(null),
            'effect':evidence.effect,'unit':evidence.unit,'causal_effect_established':False,
            'new_empirical_fact_predicted':False,'reasoning_kind':'classification_of_observed_statistical_evidence'}
    # Правило сопоставления p и 95% CI применяется только при alpha=0,05.
    require(threshold == Decimal('0.05'), 'Only a declared 0.05/95% pair is supported')
    if p is None or interval is None:
        return {**base,'label':'insufficient_data','reason':'p_or_ci_not_reported','point_direction':None}
    more_decline = (estimate > null) == evidence.higher_means_more_decline if estimate != null else None
    point = None if more_decline is None else ('more_decline' if more_decline else 'less_decline')
    detected_p = p < threshold
    detected_ci = not (interval[0] <= null <= interval[1])
    if detected_p != detected_ci:
        return {**base,'label':'requires_review','reason':'p_and_ci_disagree_or_rounded','point_direction':point}
    if not detected_p:
        return {**base,'label':'not_statistically_detected','reason':'p_at_least_alpha_and_ci_contains_null','point_direction':point}
    require(point is not None, 'Detected effect cannot equal null')
    return {**base,'label':'positive_association' if more_decline else 'inverse_association',
            'reason':'p_below_alpha_and_ci_excludes_null','point_direction':point}

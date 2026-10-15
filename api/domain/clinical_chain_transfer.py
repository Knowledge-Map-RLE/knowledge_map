"""Допуск цепочки к гипотезе: доступность предпосылок не равна научной валидности."""
from dataclasses import dataclass
from datetime import date
from domain.article_maps import require
from domain.empirical_question_forecast import eligibility, validate_context, CONTEXT

VERSION = 'clinical-chain-transfer-1'
OPERATORS = {'measurement_to_result', 'method_application', 'limitation_to_task',
             'model_validation', 'clinical_transfer'}
AVAILABILITY = {'known_before_forecast', 'requires_target_followup', 'intended_task'}


@dataclass(frozen=True)
class PremiseNode:
    node_id: str
    availability: str


@dataclass(frozen=True)
class Support:
    family: str
    available_on: str
    author_use_verified: bool
    context: dict


@dataclass(frozen=True)
class ChainCase:
    case_id: str
    operator: str
    scope: str
    nodes: tuple[PremiseNode, ...]
    edges: tuple[tuple[str, str], ...]
    conclusion_id: str
    premise_groups: tuple[tuple[str, ...], ...]
    supports: tuple[Support, ...]

    def validate(self):
        require(bool(self.case_id) and isinstance(self.case_id, str), 'Case id required')
        require(self.operator in OPERATORS, 'Unknown transfer operator')
        require(self.scope in {'isolated_IL6', 'multi_marker', 'other_exposure', 'method', 'research_task'}, 'Unknown scope')
        ids = {n.node_id for n in self.nodes}
        require(len(ids) == len(self.nodes) and all(isinstance(i, str) and i for i in ids), 'Unique node ids required')
        require(self.conclusion_id in ids, 'Unknown conclusion')
        require(all(n.availability in AVAILABILITY for n in self.nodes), 'Unknown premise availability')
        require(len(set(self.edges)) == len(self.edges), 'Repeated edge')
        require(all(a in ids and b in ids and a != b for a, b in self.edges), 'Unknown edge or self-loop')
        # Проверка всего видимого DAG; скрытые семантические отношения сюда не входят.
        incoming = {i: set() for i in ids}
        for a, b in self.edges: incoming[b].add(a)
        pending = {i: set(v) for i, v in incoming.items()}
        while pending:
            ready = {i for i, v in pending.items() if not v}
            require(bool(ready), 'Visible dependency cycle')
            pending = {i: v - ready for i, v in pending.items() if i not in ready}
        require(bool(self.premise_groups), 'Explicit joint or alternative premise groups required')
        require(len({frozenset(g) for g in self.premise_groups}) == len(self.premise_groups), 'Repeated premise group')
        for group in self.premise_groups:
            require(1 <= len(group) <= 3 and len(set(group)) == len(group), 'One to three distinct premises required')
            require(set(group) <= incoming[self.conclusion_id], 'Premise group must use immediate incoming edges')
        require(set().union(*map(set, self.premise_groups)) == incoming[self.conclusion_id], 'Ungrouped immediate premise')
        for support in self.supports:
            require(isinstance(support.family, str) and bool(support.family), 'Support family required')
            require(date.fromisoformat(support.available_on).isoformat() == support.available_on, 'Exact support date required')
            require(type(support.author_use_verified) is bool, 'Explicit grounding status required')
            validate_context(support.context)


def assess_transfer(case: ChainCase, context: dict, as_of: str, excluded_families: tuple[str, ...]):
    """Не обучает правила и не оценивает цель; проверяет явный кандидат без AI."""
    case.validate()
    validate_context(context)
    require(date.fromisoformat(as_of).isoformat() == as_of, 'Exact forecast date required')
    require(bool(excluded_families) and all(isinstance(f, str) and f for f in excluded_families), 'Heldout families required')
    parents = {n.node_id: set() for n in case.nodes}
    availability = {n.node_id: n.availability for n in case.nodes}
    for a, b in case.edges: parents[b].add(a)
    paths = []
    for group in case.premise_groups:
        closure, frontier = set(), list(group)
        while frontier:
            node = frontier.pop()
            if node in closure: continue
            closure.add(node); frontier.extend(parents[node])
        blockers = sorted(n for n in closure if availability[n] != 'known_before_forecast')
        paths.append({'premises': list(group), 'ancestors': sorted(closure), 'unavailable': blockers,
                      'available_before_forecast': not blockers})
    reasons = list(eligibility(context))
    if case.operator != 'clinical_transfer': reasons.append('operator_is_not_clinical_transfer')
    if case.scope != 'isolated_IL6': reasons.append('scope_is_not_isolated_IL6')
    if not any(p['available_before_forecast'] for p in paths): reasons.append('no_available_premise_path')
    accepted, excluded = set(), []
    for support in case.supports:
        why = list(eligibility(support.context))
        if not support.author_use_verified: why.append('author_use_not_verified')
        if support.family in excluded_families: why.append('heldout_family')
        if support.available_on >= as_of: why.append('not_strictly_earlier')
        # Здесь требуется точная применимость; сходство допускает отдельное ранжирование.
        for key in sorted(CONTEXT):
            if context[key] is None or support.context[key] is None: why.append('unknown_context:' + key)
            elif context[key] != support.context[key]: why.append('different_context:' + key)
        if why: excluded.append({'family': support.family, 'reasons': sorted(set(why))})
        else: accepted.add(support.family)
    if len(accepted) < 2: reasons.append('fewer_than_two_applicable_independent_families')
    return {'version': VERSION, 'case_id': case.case_id, 'operator': case.operator, 'scope': case.scope,
            'premise_paths': paths, 'applicable_families': sorted(accepted), 'excluded_supports': excluded,
            'status': 'candidate_for_sealed_test' if not reasons else 'not_ready',
            'reasons': sorted(set(reasons)), 'scientific_success': False,
            'rule_learning_performed': False, 'forecast_generated': False}

"""Заранее заданная проверка ограничений переноса; выбор победителя по удержанной цели запрещён."""
from copy import deepcopy
from dataclasses import replace
from itertools import combinations

from domain.article_maps import fingerprint, require
from domain.dual_question_outcomes import DualOutcomeEngine, directional_views
from domain.qualitative_question_prediction import IDENTITY, learn_rules
from domain.question_prediction import generate_question_candidates
from domain.research_semantics import context_value
from domain.structured_question_context import compare_features

VERSION = 'question-context-modifiers-1'
MODIFIERS = ('mci', 'outcome', 'adjustments')
VARIANTS = [tuple(c) for n in range(4) for c in combinations(MODIFIERS, n)]


def variant_id(selected):
    return '+'.join(selected) or 'broad'


def validate_modifier_policy(raw):
    require(set(raw) == {'version', 'variants', 'matching', 'minimum_independent_families',
                         'confirmatory', 'select_winner', 'corpus_expansion'}, 'Modifier policy fields differ')
    require(raw['version'] == VERSION and raw['variants'] == [list(v) for v in VARIANTS]
            and raw['matching'] == 'exact_normalized_feature_with_unknown_blocking'
            and type(raw['minimum_independent_families']) is int and raw['minimum_independent_families'] == 2
            and raw['confirmatory'] is False and raw['select_winner'] is False
            and raw['corpus_expansion'] is False, 'Frozen complete modifier grid required')
    return deepcopy(raw)


def selected_context(profile, selected):
    require(tuple(selected) in VARIANTS, 'Unknown modifier variant')
    comparison = compare_features(profile, profile)
    unknown = [name for name in selected if name in comparison['unknown'] or profile[name]['status'] != 'known']
    return {'values': {name: deepcopy(profile[name]) for name in selected}, 'unknown': unknown,
            'eligible': not unknown, 'knowledge_equivalence_confirmed': False}


def compare_selected(left, right, selected):
    a, b = selected_context(left, selected), selected_context(right, selected)
    unknown = sorted(set(a['unknown'] + b['unknown']))
    differences = [name for name in selected if name not in unknown and a['values'][name] != b['values'][name]]
    return {'unknown': unknown, 'differences': differences, 'eligible': not unknown and not differences,
            'knowledge_equivalence_confirmed': False}


def stratified_baseline(views, contexts, min_families):
    groups = {}
    for key, view in sorted(views.items()):
        values = contexts[key]['values']; group = groups.setdefault(fingerprint(values), {
            'application_modifiers': values, 'anchor': view, 'family_labels': {}})
        group['family_labels'].setdefault(view.evidence.family, set()).add(view.modality)
    forecasts, details = [], []
    for key, group in sorted(groups.items()):
        votes = {family: next(iter(labels)) for family, labels in sorted(group['family_labels'].items()) if len(labels) == 1}
        ambiguous = sorted(family for family, labels in group['family_labels'].items() if len(labels) > 1)
        counts = {label: sum(v == label for v in votes.values()) for label in sorted(set(votes.values()))}
        best = max(counts.values(), default=0); winners = [label for label, count in counts.items() if count == best]
        details.append({'stratum_id': key, 'application_modifiers': group['application_modifiers'],
                        'family_votes': votes, 'ambiguous_families_excluded': ambiguous, 'counts': counts})
        if len(winners) != 1 or best < min_families:
            continue
        prop = group['anchor'].proposition
        prop = {**prop, 'context': {k: v for k, v in prop['context'].items() if k not in IDENTITY}, 'modality': winners[0]}
        forecasts.append({'id': fingerprint(prop), 'status': 'stratified_family_majority_baseline',
                          'finding': winners[0], 'proposition': prop, 'application_modifiers': group['application_modifiers'],
                          'family_votes': votes, 'ambiguous_families_excluded': ambiguous,
                          'support': best, 'ranking_score': best / len(votes), 'confirmation_eligible': False})
    return sorted(forecasts, key=lambda c: (-c['ranking_score'], c['id'])), details


class ContextModifierEngine(DualOutcomeEngine):
    """Меняет только исследовательский канал знака; строгие исходы и правила DAG сохраняются."""
    def __init__(self, profiles, transport, modifier_policy, selected):
        super().__init__(profiles, transport)
        self.modifier_policy = validate_modifier_policy(modifier_policy)
        require(tuple(selected) in VARIANTS, 'Unknown modifier variant')
        self.selected = tuple(selected)
        self.analysis_binding.update(modifier_version=VERSION, modifier_policy_sha256=fingerprint(self.modifier_policy),
                                     modifier_variant=variant_id(self.selected))

    def fit(self, claims, episodes, maps, question, policy):
        require(policy.min_families == self.modifier_policy['minimum_independent_families'], 'Modifier support differs')
        result = super().fit(claims, episodes, maps, question, policy)
        views, rows = directional_views(claims, self.profiles, question, policy, self.transport)
        contexts = {}
        for row in rows:
            key = tuple(row['reference'])
            context = selected_context(self.profiles[key]['normalized'], self.selected)
            contexts[key] = context
            row['modifier_context'] = context
        views = {key: view for key, view in views.items() if contexts[key]['eligible']}
        for key, view in list(views.items()):
            token = context_value('modifier_context:' + fingerprint(contexts[key]['values']))
            views[key] = replace(view, context={**view.context, 'stratum': token, 'conditions': token})
        modes, rules, diagnostics = {}, {}, {}
        def context_check(a, b):
            compared = compare_selected(self.profiles[a.evidence.article_id, a.claim_id]['normalized'],
                                        self.profiles[b.evidence.article_id, b.claim_id]['normalized'], self.selected)
            return ['unknown:' + name for name in compared['unknown']] + ['feature:' + name for name in compared['differences']]
        for mode in ('semantic', 'dependency'):
            learned, stats = learn_rules(claims, views, episodes, maps, question, policy,
                                         mode == 'dependency', context_check=context_check)
            candidates, bounded = generate_question_candidates(views, learned, question)
            candidates = [c for c in candidates if not set(c['abstracted_context_fields']) - IDENTITY]
            for c in candidates:
                premise = c['premises'][0]; key = (premise['evidence']['article_id'], premise['claim_id'])
                c.update(status='modifier_bounded_direction_hypothesis', finding=c['proposition']['modality'],
                         application_modifiers=deepcopy(contexts[key]['values']), confirmation_eligible=False,
                         numerical_evidence=[claims[p['evidence']['article_id'], p['claim_id']].to_dict() for p in c['premises']])
            modes[mode], rules[mode], diagnostics[mode] = candidates, learned, {**stats, 'bounded_searches': bounded}
        modes['family_frequency_baseline'], groups = stratified_baseline(views, contexts, policy.min_families)
        result['outcome_channels']['reported_direction_exploratory'] = {
            'modes': modes, 'rules': rules, 'diagnostics': diagnostics, 'observations': rows,
            'modifier_variant': variant_id(self.selected), 'selected_modifiers': list(self.selected),
            'eligible_modifier_claims': len(views),
            'eligible_modifier_families': sorted({v.evidence.family for v in views.values()}),
            'unknown_modifier_claims': [r['reference'] for r in rows if not r['modifier_context']['eligible']],
            'baseline_strata': groups, 'transport_policy': deepcopy(self.transport),
            'modifier_policy': deepcopy(self.modifier_policy), 'confirmation_eligible': False,
            'point_sign_is_not_biological_truth': True}
        return result

    def evaluate(self, sealed, targets):
        # Родитель проверяет даты, удержание семьи и независимый строгий канал.
        result = super().evaluate(sealed, targets)
        channel = result['outcome_channels']['reported_direction_exploratory']
        for target in channel['targets']:
            target['modifier_context'] = selected_context(self.profiles[tuple(target['reference'])]['normalized'], self.selected)
        for mode, candidates in sealed['outcome_channels']['reported_direction_exploratory']['modes'].items():
            rows = []
            for candidate in candidates:
                for target in channel['targets']:
                    values = target['modifier_context']; application = candidate['application_modifiers']
                    differences = [name for name in self.selected if name not in values['unknown'] and application[name] != values['values'][name]]
                    raw, prop, direction = target['original'], candidate['proposition'], target['direction']
                    same_logic = all(raw[k] == prop[k] for k in ('predicate', 'roles', 'negated', 'quantifier', 'action_status', 'logic'))
                    scorable = bool(direction['label']) and target['transport_scope']['eligible'] and same_logic and not differences and not values['unknown']
                    rows.append({'prediction_id': candidate['id'], 'target': target['reference'],
                                 'status': ('point_sign_agreement' if direction['label'] == candidate['finding'] else 'different_point_sign') if scorable else 'unscorable',
                                 'predicted': candidate['finding'], 'observed': direction['label'],
                                 'supported_target_direction': direction['supported_direction'], 'direction_evidence': direction,
                                 'modifier_comparison': {'unknown': values['unknown'], 'differences': differences},
                                 'scope_eligible': target['transport_scope']['eligible'], 'same_logic': same_logic,
                                 'true_biological_direction_confirmed': False})
            scored = [r for r in rows if r['status'] != 'unscorable']
            agreements = sum(r['status'] == 'point_sign_agreement' for r in scored)
            channel['modes'][mode] = {'issued_answers': len(candidates), 'claim_comparisons': len(rows),
                'scorable_comparisons': len(scored), 'unscorable_comparisons': len(rows) - len(scored),
                'agreements': agreements, 'different_signs': len(scored) - agreements,
                'point_sign_agreement_rate': agreements / len(scored) if scored else None,
                'target_families': sorted({t['original']['evidence']['family'] for t in channel['targets']}),
                'supported_target_comparisons': sum(r['supported_target_direction'] for r in scored),
                'results': rows, 'multiple_estimates_are_not_independent_trials': True, 'confirmation_eligible': False}
        return result

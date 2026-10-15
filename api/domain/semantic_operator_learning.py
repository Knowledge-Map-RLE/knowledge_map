"""Обучение семантических операторов по авторским группам предпосылок, без AI."""
from dataclasses import dataclass, asdict
from collections import defaultdict
from datetime import date
from itertools import permutations, product
import json
from domain.article_maps import fingerprint, require
from domain.empirical_question_forecast import validate_context, eligibility, CONTEXT

VERSION = 'semantic-operator-learning-1'
KINDS = {'clinical_transfer', 'measurement_to_result', 'method_application', 'limitation_to_task', 'model_validation'}
CHANNELS = {'clinical': {'clinical_transfer'}, 'research_task': {'limitation_to_task'},
            'method': {'method_application'}, 'reconstruction': {'measurement_to_result', 'model_validation'}}
VARIABLE_ROLES = {'clinical_transfer': {'cohort'}, 'limitation_to_task': {'cohort', 'research object'},
                  'method_application': {'cohort'}, 'measurement_to_result': {'cohort'}, 'model_validation': {'cohort'}}
LIMITS = {'min_families': 2, 'max_premises': 3, 'max_search_steps': 10000, 'prediction_limit': 20}


@dataclass(frozen=True)
class Knowledge:
    claim_id: str
    source_id: str
    family: str
    published_on: str
    frame: dict
    availability: str
    binding: dict
    question_context: dict | None = None

    def validate(self):
        require(all(isinstance(v, str) and bool(v) for v in (self.claim_id, self.source_id, self.family)), 'Knowledge identity required')
        require(date.fromisoformat(self.published_on).isoformat() == self.published_on, 'Exact publication date required')
        require(self.availability in {'known_before_forecast', 'requires_target_followup', 'intended_task'}, 'Explicit availability required')
        validate_frame(self.frame)
        require(set(self.binding) == {'source_sha256', 'run_id', 'frame_sha256', 'provenance'}, 'Exact semantic binding required')
        require(self.binding['frame_sha256'] == fingerprint(self.frame), 'Semantic frame hash differs')
        require(isinstance(self.binding['run_id'], str) and bool(self.binding['run_id']), 'Source run required')
        require(isinstance(self.binding['source_sha256'], str) and len(self.binding['source_sha256']) == 64
                and all(c in '0123456789abcdef' for c in self.binding['source_sha256']), 'Invalid source digest')
        require(isinstance(self.binding['provenance'], list) and bool(self.binding['provenance']), 'Provenance required')
        if self.question_context is not None: validate_context(self.question_context)


@dataclass(frozen=True)
class Example:
    example_id: str
    operator: str
    premises: tuple[str, ...]
    conclusion: str
    author_grounded: bool


def validate_frame(frame):
    require(isinstance(frame, dict) and set(frame) == {'kind', 'action_status', 'logic', 'statements'}, 'Exact frame fields required')
    require(frame['kind'] in {'state', 'action'}, 'State or action required')
    require(frame['action_status'] in ({None} if frame['kind'] == 'state' else {'performed', 'intended', 'unresolved'}), 'Explicit action status required')
    require(frame['logic'] in {'single', 'conjunction', 'contrast', 'argument'}, 'Unknown frame logic')
    require(isinstance(frame['statements'], list) and bool(frame['statements']), 'Semantic statements required')
    require(frame['logic'] != 'single' or len(frame['statements']) == 1, 'Single frame must contain one statement')
    for s in frame['statements']:
        require(set(s) == {'predicate', 'roles', 'scope', 'attributes', 'negated', 'unknown_context'}, 'Exact semantic statement required')
        require(isinstance(s['predicate'], str) and bool(s['predicate']), 'Predicate required')
        require(type(s['negated']) is bool and type(s['unknown_context']) is bool, 'Explicit semantic flags required')
        require(isinstance(s['scope'], dict) and set(s['scope']) == {'quantifier', 'modality', 'time', 'conditions'}, 'Exact scope required')
        require(all(s['scope'][k] is None or isinstance(s['scope'][k], str) for k in ('quantifier', 'modality', 'time')), 'Invalid scope value')
        require(isinstance(s['scope']['conditions'], list) and all(isinstance(c, str) for c in s['scope']['conditions']), 'Explicit conditions required')
        require(isinstance(s['attributes'], list), 'Attributes required')
        for a in s['attributes']:
            require(set(a) == {'name', 'value', 'unit'} and isinstance(a['name'], str), 'Invalid semantic attribute')
            require(a['unit'] is None or isinstance(a['unit'], str), 'Invalid unit')
        require(isinstance(s['roles'], list) and bool(s['roles']), 'Participant roles required')
        require(len({r['role'] for r in s['roles']}) == len(s['roles']), 'Repeated semantic role')
        require(all(set(r) == {'role', 'value'} and isinstance(r['role'], str) and isinstance(r['value'], str) for r in s['roles']), 'Resolved role values required')
    fingerprint(frame)


def frame_ready(frame):
    return all(not s['unknown_context'] for s in frame['statements'])


def ordered_frame(frame):
    # Порядок частей противопоставления/аргумента сохраняется; роли не зависят от порядка JSON.
    return {**frame, 'statements': [{**s, 'roles': sorted(s['roles'], key=lambda r: r['role']),
                                    'attributes': sorted(s['attributes'], key=fingerprint),
                                    'scope': {**s['scope'], 'conditions': sorted(s['scope']['conditions'])}}
                                   for s in frame['statements']]}


def template_for(body, head, operator):
    variants = []
    for ordered in permutations(body):
        variables = {}
        def abstract(frame, create):
            output = ordered_frame(frame)
            statements = []
            for s in output['statements']:
                roles = []
                for r in s['roles']:
                    value = r['value']
                    if r['role'] in VARIABLE_ROLES[operator] and not value.startswith('knowledge:'):
                        key = (r['role'], value)
                        if key not in variables:
                            if not create: return None
                            variables[key] = '$' + str(len(variables))
                        term = {'variable': variables[key]}
                    else: term = {'constant': value}
                    roles.append({'role': r['role'], 'term': term})
                statements.append({**s, 'roles': roles})
            return {**output, 'statements': statements}
        premises = [abstract(k.frame, True) for k in ordered]
        conclusion = abstract(head.frame, False)
        if conclusion is not None:
            value = {'operator': operator, 'premises': premises, 'conclusion': conclusion,
                     'clinical_context': head.question_context if operator == 'clinical_transfer' else None}
            variants.append((json.dumps(value, sort_keys=True, ensure_ascii=False), value, ordered))
    return min(variants, key=lambda v: v[0]) if variants else None


def learn(knowledge, examples, as_of, excluded_families):
    require(date.fromisoformat(as_of).isoformat() == as_of and bool(excluded_families), 'Explicit cutoff and heldout families required')
    claims = {k.claim_id: k for k in knowledge}
    require(len(claims) == len(knowledge), 'Duplicate knowledge identity')
    require(len({e.example_id for e in examples}) == len(examples), 'Duplicate example identity')
    for k in knowledge: k.validate()
    grouped, rejected = {}, []
    for e in sorted(examples, key=lambda e: e.example_id):
        require(e.operator in KINDS and type(e.author_grounded) is bool, 'Unknown operator or grounding')
        require(1 <= len(e.premises) <= 3 and len(set(e.premises)) == len(e.premises), 'One to three joint premises required')
        require(e.conclusion in claims and all(p in claims for p in e.premises) and e.conclusion not in e.premises, 'Unknown example reference')
        body, head = [claims[p] for p in e.premises], claims[e.conclusion]
        require(len({k.source_id for k in [*body, head]}) == len({k.family for k in [*body, head]}) == 1, 'Example must belong to one source and family')
        reasons = []
        if not e.author_grounded: reasons.append('author_use_not_grounded')
        if any(k.family in excluded_families for k in [*body, head]): reasons.append('heldout_family')
        if any(k.published_on >= as_of for k in [*body, head]): reasons.append('not_strictly_earlier')
        if any(not frame_ready(k.frame) for k in [*body, head]): reasons.append('unknown_context_or_unresolved_reference')
        if e.operator == 'clinical_transfer' and any(k.availability != 'known_before_forecast' for k in body): reasons.append('requires_new_outcome')
        if e.operator == 'clinical_transfer':
            contexts = [k.question_context for k in [*body, head]]
            if any(c is None or eligibility(c) or any(c[key] is None for key in CONTEXT) for c in contexts):
                reasons.append('incomplete_or_ineligible_clinical_context')
            elif any(c != contexts[0] for c in contexts): reasons.append('different_clinical_context')
        if any(ordered_frame(k.frame) == ordered_frame(head.frame) for k in body): reasons.append('conclusion_repeats_premise')
        if reasons:
            rejected.append({'example_id': e.example_id, 'reasons': reasons}); continue
        variant = template_for(body, head, e.operator)
        if variant is None:
            rejected.append({'example_id': e.example_id, 'reasons': ['unbound_conclusion_participant']}); continue
        key, template, ordered = variant
        rule = grouped.setdefault(key, {'operator_id': fingerprint(template), **template, 'support_families': set(), 'examples': []})
        rule['support_families'].add(head.family)
        rule['examples'].append({'example_id': e.example_id, 'source_id': head.source_id, 'family': head.family,
                                 'premises': [k.claim_id for k in ordered], 'conclusion': head.claim_id,
                                 'bindings': [k.binding for k in [*ordered, head]]})
    rules, candidates = [], []
    for row in grouped.values():
        item = {**row, 'support_families': sorted(row['support_families']), 'support': len(row['support_families']),
                'status': 'statistical_operator_hypothesis'}
        (rules if item['support'] >= 2 else candidates).append(item)
    key = lambda r: (-r['support'], r['operator_id'])
    return {'version': VERSION, 'limits': LIMITS, 'rules': sorted(rules, key=key),
            'unsupported_templates': sorted(candidates, key=key), 'rejected_examples': rejected,
            'scientific_success': False, 'model_calls': 0}


def bind(template, frame, bindings):
    frame = ordered_frame(frame)
    if any(template[k] != frame[k] for k in ('kind', 'action_status', 'logic')) or len(template['statements']) != len(frame['statements']): return None
    result = dict(bindings)
    for a, b in zip(template['statements'], frame['statements']):
        if any(a[k] != b[k] for k in ('predicate', 'scope', 'attributes', 'negated', 'unknown_context')): return None
        if [r['role'] for r in a['roles']] != [r['role'] for r in b['roles']]: return None
        for r, actual in zip(a['roles'], b['roles']):
            term, value = r['term'], actual['value']
            if 'constant' in term:
                if term['constant'] != value: return None
            else:
                name = term['variable']
                if name in result and result[name] != value: return None
                result[name] = value
    return result


def instantiate(template, bindings):
    return {**template, 'statements': [{**s, 'roles': [{'role': r['role'], 'value': r['term'].get('constant', bindings.get(r['term'].get('variable')))}
                                                      for r in s['roles']]} for s in template['statements']]}


def apply(learned, available, as_of, channel, excluded_families):
    require(learned['version'] == VERSION and channel in CHANNELS, 'Compatible operator version and channel required')
    require(date.fromisoformat(as_of).isoformat() == as_of and bool(excluded_families), 'Explicit application cutoff and heldout families required')
    require(len({k.claim_id for k in available}) == len(available), 'Duplicate application knowledge')
    for k in available: k.validate()
    accepted, excluded = [], []
    for k in available:
        why = []
        if k.availability != 'known_before_forecast': why.append('premise_not_available')
        if not frame_ready(k.frame): why.append('unknown_context')
        if k.published_on >= as_of: why.append('not_strictly_earlier')
        if why: excluded.append({'claim_id': k.claim_id, 'reasons': why})
        else: accepted.append(k)
    # Все совместные входы привязаны к одной конкретной статье, семьи не смешиваются.
    groups = defaultdict(list)
    for k in accepted: groups[(k.source_id, k.family)].append(k)
    predictions, steps, truncated = {}, 0, False
    known = {(k.source_id, fingerprint(ordered_frame(k.frame))) for k in accepted}
    for rule in learned['rules']:
        require(rule['support'] == len(set(rule['support_families'])) >= 2, 'Independent support required')
        if rule['operator'] not in CHANNELS[channel] or set(rule['support_families']) & set(excluded_families): continue
        for (source_id, family), records in sorted(groups.items()):
            candidates = [[k for k in records if bind(t, k.frame, {}) is not None
                           and (rule['operator'] != 'clinical_transfer' or k.question_context == rule['clinical_context'])]
                          for t in rule['premises']]
            for combo in product(*candidates):
                if steps >= LIMITS['max_search_steps']: truncated = True; break
                steps += 1
                if len({k.claim_id for k in combo}) != len(combo): continue
                bindings = {}
                for template, k in zip(rule['premises'], combo):
                    bindings = bind(template, k.frame, bindings)
                    if bindings is None: break
                if bindings is None: continue
                # Разные локальные участники не сливаются ради совпадения шаблона.
                if len(set(bindings.values())) != len(bindings): continue
                frame = instantiate(rule['conclusion'], bindings)
                validate_frame(frame)
                if (source_id, fingerprint(frame)) in known: continue
                identity = fingerprint({'source_id': source_id, 'frame': frame, 'operator_id': rule['operator_id']})
                predictions[identity] = {'id': identity, 'frame': frame, 'source_id': source_id, 'family': family,
                                         'operator_id': rule['operator_id'], 'operator': rule['operator'],
                                         'support_families': rule['support_families'], 'support': rule['support'],
                                         'premises': [{'claim_id': k.claim_id, 'binding': k.binding} for k in combo],
                                         'status': 'statistical_hypothesis', 'scientific_success': False}
            if truncated: break
        if truncated: break
    ranked = sorted(predictions.values(), key=lambda p: (-p['support'], len(p['premises']), p['id']))
    return {'channel': channel, 'predictions': ranked[:20], 'search_steps': steps, 'search_truncated': truncated,
            'eligible_premises': len(accepted), 'excluded_premises': excluded, 'scientific_success': False}

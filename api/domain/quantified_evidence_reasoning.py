"""Арифметическая интерпретация напечатанных p не создаёт эмпирический эффект."""
from collections import Counter, defaultdict
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import re

from domain.article_maps import require, fingerprint, ArticleMapError
from domain.semantic_operator_graph import VERSION as GRAPH_VERSION

VERSION = 'source-bound-printed-p-comparison-1'
DECIMAL = r'(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d{1,3})?'
OPERAND = re.compile(r'\s*(<=|>=|<|>|≤|≥)?\s*(' + DECIMAL + r')\s*')
PREDICATES = frozenset({'estimated hazard ratio', 'estimated cognitive level difference',
    'estimated instantaneous rate difference', 'regression coefficient', 'partial correlation',
    'estimated association', 'group comparison', 'estimated cognitive slope', 'risk index component'})
DECISIONS_RU = {'below': 'Напечатанное значение или указанный диапазон ниже порога',
    'not_below': 'Напечатанное значение или указанный диапазон не ниже порога',
    'undetermined': 'Указанного диапазона недостаточно для решения'}


def parse_reported_operand(raw):
    require(isinstance(raw, str) and len(raw) <= 100, 'Explicit short reported decimal string required')
    match = OPERAND.fullmatch(raw)
    require(match is not None, 'Unrecognized reported operand; footnotes and unknown tokens must not be dropped')
    op = {'≤': '<=', '≥': '>='}.get(match[1], match[1])
    try: value = Decimal(match[2])
    except InvalidOperation as error: raise ArticleMapError('Invalid reported decimal') from error
    require(value.is_finite() and 0 <= value <= 1, 'Reported probability operand outside [0,1]')
    require(not (op == '<' and value == 0) and not (op == '>' and value == 1), 'Empty reported probability interval')
    return op, value


def compare_printed_p(p, alpha):
    """Сравнивается напечатанное число либо явно сообщённая граница, не скрытое точное p."""
    op, value = parse_reported_operand(p); alpha_op, cutoff = parse_reported_operand(alpha)
    require(alpha_op is None and cutoff > 0, 'Exact positive printed threshold required')
    if op is None:
        decision = 'below' if value < cutoff else 'not_below'
    elif op in ('<', '<='):
        decision = 'below' if value < cutoff or (value == cutoff and op == '<') else 'undetermined'
    else:
        decision = 'not_below' if value >= cutoff else 'undetermined'
    return {'decision': decision, 'comparison': 'strict_less_than', 'reported_p': p,
        'reported_alpha': alpha, 'p_bound_operator': op, 'unrounded_p_decision_established': False,
        'biological_effect_or_absence_established': False,
        'rounding_policy_ru': 'Для числа без знака сравнивается только напечатанное значение. '
            'Округление и точное ненапечатанное p неизвестны. Явная граница сохраняется как утверждение источника.'}


def reason_over_quantified_evidence(graph):
    require(graph['version'] == GRAPH_VERSION and graph['question'] is None and graph['model_calls'] == 0,
        'Complete source-only graph required')
    parents = graph['parents']; grouped = defaultdict(list)
    require(len(parents) == graph['canonical_blocks'] and len(graph['statements']) == graph['statement_count'], 'Whole quantitative graph coverage differs')
    for s in graph['statements'].values():
        require(s['parent'] in parents, 'Unknown quantitative parent')
        grouped[s['parent']].append(s)
    require(set(grouped) == set(parents), 'Every canonical block must be represented')
    proofs, coverage, counts = [], [], Counter()
    for pid, parent in sorted(parents.items()):
        native = parent['complete_parent']; require(fingerprint(native) == parent['knowledge_sha256'], 'Complete quantitative parent changed')
        rows = []; operations = []
        statements = sorted(grouped[pid], key=lambda s: s['position'])
        require([s['original_statement'] for s in statements] == native['semantic_frame']['statements'], 'Quantitative statement coverage differs')
        for s in statements:
            attrs = s['original_statement']['qualifiers']['attributes']
            # Имена исходных полей проверяются явно. Неизвестная единица и сноска не исправляются догадкой.
            ps = [(i, a) for i, a in enumerate(attrs) if a['name'] == 'p']
            alphas = [(i, a) for i, a in enumerate(attrs) if a['name'] == 'alpha']
            reason = None
            if s['state_or_action'] != 'state': reason = 'action_not_a_reported_measurement'
            elif s['predicate'] not in PREDICATES: reason = 'no_registered_statistical_operand_meaning'
            elif s['unknown_context']: reason = 'unresolved_context'
            elif s['scope']['modality'] is not None or s['negated']: reason = 'modal_or_negated_measurement'
            elif not ps or not alphas: reason = 'explicit_same_statement_p_and_alpha_required'
            elif len(ps) != 1 or len(alphas) != 1: reason = 'ambiguous_operand_attributes'
            elif any(a['unit'] != 'dimensionless' for _, a in [*ps, *alphas]): reason = 'dimensionless_operands_required'
            if reason is None:
                try: operation = compare_printed_p(ps[0][1]['value'], alphas[0][1]['value'])
                except ArticleMapError:
                    reason = 'unrecognized_or_inconsistent_reported_operand'
                else:
                    # Ошибки доменного контракта не поглощаются общим исключением.
                    evidence = []
                    for eid in s['evidence']:
                        e = graph['source_units'][eid]
                        require(e['article_id'] == parent['article_id'] and e['source_sha256'] == parent['source_sha256']
                            and sha256(e['text'].encode()).hexdigest() == e['sha256'] and len(e['text']) == e['end'] - e['start'],
                            'Quantitative source evidence changed')
                        evidence.append(deepcopy(e))
                    require(bool(evidence), 'Quantitative operands lack source evidence')
                    operations.append({'statement_id': s['statement_id'], 'statement_position': s['position'],
                        'operation': operation, 'reason_ru': DECISIONS_RU[operation['decision']],
                        'scope': deepcopy(s['scope']), 'roles': deepcopy(s['roles']),
                        'operand_positions': {'p': ps[0][0], 'alpha': alphas[0][0]}, 'evidence': evidence})
                    counts[operation['decision']] += 1
            status = reason or 'printed_comparison_computed'
            rows.append({'statement_id': s['statement_id'], 'status': status})
            if reason: counts[reason] += 1
        coverage.append({'parent': pid, 'article_id': parent['article_id'], 'knowledge_id': parent['knowledge_id'],
            'all_statement_decisions': rows, 'all_parts_retained': True})
        if operations:
            proof = {'version': VERSION, 'parent': pid, 'article_id': parent['article_id'],
                'knowledge_id': parent['knowledge_id'], 'run_id': parent['run_id'],
                'source_sha256': parent['source_sha256'], 'graph_sha256': parent['graph_sha256'],
                'complete_parent': deepcopy(native), 'complete_parent_sha256': parent['knowledge_sha256'],
                'parent_logic': native['semantic_frame']['logic'], 'operations': operations,
                'all_statement_decisions': rows, 'status': 'derived_interpretation_of_reported_numbers',
                'operator_origin': 'explicit_mathematical_comparison_not_empirically_learned',
                'parts_asserted_as_independent_facts': False, 'new_measurement': False,
                'new_empirical_prediction': False, 'graph_dependencies_used': False}
            proof['id'] = fingerprint(proof); proofs.append(proof)
    return {'version': VERSION, 'question': None, 'model_calls': 0, 'target_read': False,
        'canonical_blocks': len(parents), 'statement_count': graph['statement_count'],
        'proofs': proofs, 'coverage': coverage, 'counts': dict(counts), 'new_predictions': [],
        'scientific_success': False, 'graph_advantage_demonstrated': False,
        'policy_ru': 'Оператор сравнивает сообщённые p и alpha одного утверждения и сохраняет полный составной блок. '
            'Он не выводит биологическое отсутствие эффекта, причинность, размер нового эффекта или его будущую значимость. '
            'Иные пороги, соседние статьи и ненапечатанное точное p не подставляются.'}

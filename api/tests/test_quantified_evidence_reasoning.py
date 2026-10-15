"""Напечатанные числа, границы, составные блоки и неизвестность не смешиваются."""
from copy import deepcopy
import pytest

from domain.article_maps import ArticleMapError
from domain.quantified_evidence_reasoning import compare_printed_p, reason_over_quantified_evidence
from domain.semantic_operator_graph import build_graph
from tests.test_semantic_operator_graph import fixture


def measured_map(p='.01', alpha='.05'):
    m = fixture(); s = m['graph']['knowledge'][0]['semantic_frame']['statements'][0]
    s['predicate'] = 'estimated hazard ratio'
    s['qualifiers']['attributes'] = [{'name': 'p', 'value': p, 'unit': 'dimensionless'},
        {'name': 'alpha', 'value': alpha, 'unit': 'dimensionless'},
        {'name': 'estimate', 'value': '2.5', 'unit': 'dimensionless'}]
    return m


@pytest.mark.parametrize('p,alpha,decision', [('.01', '.05', 'below'), ('.05', '.05', 'not_below'),
    ('.06', '.05', 'not_below'), ('<.05', '.05', 'below'), ('<=.05', '.05', 'undetermined'),
    ('≤.05', '.05', 'undetermined'), ('>.05', '.05', 'not_below'), ('≥.05', '.05', 'not_below'),
    ('<.1', '.05', 'undetermined'), ('>.01', '.05', 'undetermined'), ('1e-3', '.01', 'below'),
    ('<=0', '.05', 'below'), ('>=1', '1', 'not_below'), ('1.0', '1.0', 'not_below')])
def test_exact_printed_comparison_and_explicit_boundaries(p, alpha, decision):
    result = compare_printed_p(p, alpha)
    assert result['decision'] == decision and result['comparison'] == 'strict_less_than'
    assert not result['unrounded_p_decision_established'] and not result['biological_effect_or_absence_established']


@pytest.mark.parametrize('p,alpha', [('<0', '.05'), ('>1', '.05'), ('-0.01', '.05'), ('1.1', '.05'),
    ('.01 footnote 2', '.05'), ('.001 1', '.05'), ('not reported', '.05'), ('.01', '<.05'),
    ('.01', '0'), ('NaN', '.05'), ('inf', '.05'), ('.01', '2')])
def test_invalid_ambiguous_or_footnoted_operands_are_not_corrected(p, alpha):
    with pytest.raises(ArticleMapError): compare_printed_p(p, alpha)


def test_full_parent_provenance_and_compound_vector_are_preserved():
    m = measured_map(); k = m['graph']['knowledge'][0]; k['semantic_frame']['logic'] = 'contrast'
    other = deepcopy(k['semantic_frame']['statements'][0]); other['statement_id'] = 'S4'
    other['qualifiers']['attributes'][0]['value'] = '.1'; k['semantic_frame']['statements'].append(other)
    graph = build_graph([m]); before = deepcopy(graph); result = reason_over_quantified_evidence(graph)
    assert graph == before and result['canonical_blocks'] == 3 and len(result['coverage']) == 3
    assert len(result['proofs']) == 1
    proof = result['proofs'][0]
    assert proof['complete_parent'] == k and proof['parent_logic'] == 'contrast'
    assert [r['operation']['decision'] for r in proof['operations']] == ['below', 'not_below']
    assert not proof['parts_asserted_as_independent_facts'] and not proof['new_empirical_prediction']
    assert not result['new_predictions'] and not result['graph_advantage_demonstrated']


@pytest.mark.parametrize('change,reason', [('unit', 'dimensionless_operands_required'),
    ('modality', 'modal_or_negated_measurement'), ('negated', 'modal_or_negated_measurement'),
    ('unknown_context', 'unresolved_context'), ('duplicate', 'ambiguous_operand_attributes'),
    ('missing_alpha', 'explicit_same_statement_p_and_alpha_required'),
    ('footnote', 'unrecognized_or_inconsistent_reported_operand')])
def test_operand_scope_and_contract_fail_closed(change, reason):
    m = measured_map(); s = m['graph']['knowledge'][0]['semantic_frame']['statements'][0]
    if change == 'unit': s['qualifiers']['attributes'][0]['unit'] = 'percent'
    elif change == 'modality': s['modality'] = 'may'
    elif change == 'negated': s['negated'] = True
    elif change == 'unknown_context': s['conditions'] = []
    elif change == 'duplicate': s['qualifiers']['attributes'].append(deepcopy(s['qualifiers']['attributes'][0]))
    elif change == 'missing_alpha': s['qualifiers']['attributes'].pop(1)
    elif change == 'footnote': s['qualifiers']['attributes'][0]['value'] = '.001 1'
    result = reason_over_quantified_evidence(build_graph([m]))
    assert not result['proofs'] and result['counts'][reason] == 1


def test_same_named_source_fields_do_not_merge_cohorts_or_borrow_alpha():
    one, two = measured_map(), measured_map(alpha='.001'); a = one['graph']['knowledge'][0]['semantic_frame']['statements'][0]
    a['qualifiers']['attributes'].pop(1)
    result = reason_over_quantified_evidence(build_graph([one, {**two, 'article_id': 'two', 'run_id': 'run-two'}]))
    assert len(result['proofs']) == 1 and result['proofs'][0]['article_id'] == 'two'
    assert result['proofs'][0]['operations'][0]['operation']['decision'] == 'not_below'


def test_changed_evidence_or_parent_prevents_publication():
    graph = build_graph([measured_map()]); proof = next(iter(graph['source_units'].values())); proof['text'] += 'changed'
    with pytest.raises(ArticleMapError, match='evidence changed'): reason_over_quantified_evidence(graph)
    graph = build_graph([measured_map()]); next(iter(graph['parents'].values()))['complete_parent']['display_text'] = 'changed'
    with pytest.raises(ArticleMapError, match='parent changed'): reason_over_quantified_evidence(graph)


def test_visible_dependencies_do_not_change_within_statement_arithmetic():
    graph = build_graph([measured_map()]); without = deepcopy(graph)
    without['author_dependencies'] = []; without['visible_occurrence_edges'] = []
    assert reason_over_quantified_evidence(graph) == reason_over_quantified_evidence(without)


def test_incorrect_claim_of_whole_map_coverage_is_rejected():
    graph = build_graph([measured_map()]); graph['statement_count'] += 1
    with pytest.raises(ArticleMapError, match='coverage differs'): reason_over_quantified_evidence(graph)

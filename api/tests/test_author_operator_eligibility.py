"""Связь с измерением, интерпретация и алгебраическое следствие различаются."""
from copy import deepcopy
from fractions import Fraction
from hashlib import sha256

import pytest

from application.author_operator_eligibility import AuditSealedAuthorOperators
from domain.article_maps import ArticleMapError, fingerprint
from domain.author_operator_eligibility import audit_author_operators, fit_counterexample
from infrastructure.development_prediction_store import FilePredictionStore


def fixture(arity=1, head_kind='state', head_origin='primary_result', fit=True):
    parents = {}; nodes = {}; occurrences = {}; source_sha = 'a' * 64
    def add(key, predicate, kind, origin, text):
        statement = {'statement_id': key + 'S1', 'predicate': predicate, 'qualifiers': {'attributes':
            [{'name': 'incremental_R2', 'value': 0.168, 'unit': None}] if predicate == 'incremental_model_fit' else []}}
        native = {'kind': kind, 'display_text': text, 'semantic_frame': {'statements': [statement]}}
        parents[key] = {'article_id': 'article', 'knowledge_id': key, 'source_sha256': source_sha,
                        'complete_parent': native, 'knowledge_sha256': fingerprint(native)}
        nodes['N' + key] = {'parent': key, 'origin': {'statements': [{'origin': origin}]}}
        occurrences['N' + key] = {'parent': key}
    for i in range(arity): add('P' + str(i), 'incremental_model_fit' if fit else 'estimated association', 'state', 'primary_result', 'Input')
    add('H', 'regression_coefficient' if fit else 'summary', head_kind, head_origin, 'Coefficient')
    body = ['P' + str(i) for i in range(arity)]
    text = 'Исходный фрагмент 🐁'
    evidence = {'article_id': 'article', 'source_sha256': source_sha, 'text': text, 'start': 0,
                'end': len(text), 'sha256': sha256(text.encode()).hexdigest()}
    group = {'article_id': 'article', 'head': 'H', 'premises': body, 'head_occurrence': 'NH',
             'premise_occurrences': ['N' + k for k in body], 'evidence': [evidence]}
    group['id'] = fingerprint(group)
    binding = {'metadata': {'question': None, 'excluded_source_sha256': ['b' * 64]}}
    return {'binding': binding, 'run_id': fingerprint(binding), 'model_calls': 0, 'target_read': False,
            'semantic_graph': {'parents': parents, 'visible_occurrences': occurrences, 'statement_count': len(parents)},
            'argument_circuits': {'nodes': nodes, 'canonical_blocks': len(parents), 'groups': {group['id']: group}}}


@pytest.mark.parametrize('delta', ['.168', '.174', '.246', '.242'])
@pytest.mark.parametrize('intercept', [False, True])
def test_same_fit_does_not_identify_coefficient_sign_or_intercept(delta, intercept):
    result = fit_counterexample(delta, intercept); a, b = result['models']
    assert a['variance_y'] == b['variance_y'] == '1'
    assert a['baseline_R2'] == b['baseline_R2'] and a['full_R2'] == b['full_R2']
    assert Fraction(a['full_R2']) - Fraction(a['baseline_R2']) == Fraction(delta)
    assert a['intercept'] != b['intercept'] if intercept else a['added_coefficient'] != b['added_coefficient']
    assert not result['source_patient_data_reconstructed'] and not result['applies_to_full_source_prose']


@pytest.mark.parametrize('delta', ['0', '1', '-.1', '1.1'])
def test_invalid_variance_is_rejected(delta):
    with pytest.raises(ArticleMapError): fit_counterexample(delta)


def test_fit_group_preserves_full_inputs_and_rejects_automatic_parameter_learning():
    source = fixture(); before = deepcopy(source); result = audit_author_operators(source, 3)
    assert source == before and result['counts'] == {'parameter_not_identified_by_fit_summary': 1}
    assert len(result['rows'][0]['countermodels']) == 1
    assert not result['rows'][0]['automatically_licensed_empirical_rule']


def test_variadic_group_retained_without_selecting_three_convenient_inputs():
    result = audit_author_operators(fixture(arity=21, fit=False), 3)
    assert result['groups_above_previous_arity'] == 1 and result['arity_counts'] == {'21': 1}
    row = result['rows'][0]; assert len(row['full_premises']) == len(row['premise_occurrences']) == 21
    assert row['route'] == 'result_synthesis_requires_operator_license'


@pytest.mark.parametrize('kind,origin,expected', [
    ('action', 'research_task', 'task_or_procedure_not_empirical_outcome'),
    ('state', 'primary_interpretation', 'interpretation_not_empirical_truth_label'),
    ('state', 'cited_result', 'reported_or_cited_conclusion_not_independent_support'),
    ('state', 'definition', 'definition_background_or_mixed_origin_requires_separate_license')])
def test_source_origin_is_not_a_proof_of_empirical_truth(kind, origin, expected):
    result = audit_author_operators(fixture(head_kind=kind, head_origin=origin, fit=False), 3)
    assert result['rows'][0]['route'] == expected and result['new_confirmed_predictions'] == 0


@pytest.mark.parametrize('change', ['group', 'parent', 'fragment', 'occurrence', 'target_read', 'model_calls'])
def test_changed_binding_or_scope_rejected(change):
    source = fixture(); groups = source['argument_circuits']['groups']; group = next(iter(groups.values()))
    if change == 'group': group['premises'] = []
    elif change == 'parent': source['semantic_graph']['parents']['P0']['complete_parent']['display_text'] = 'Guess'
    elif change == 'fragment': group['evidence'][0]['text'] += 'guess'
    elif change == 'occurrence': source['argument_circuits']['nodes']['NP0']['parent'] = 'H'
    elif change == 'target_read': source['target_read'] = True
    elif change == 'model_calls': source['model_calls'] = 1
    with pytest.raises(ArticleMapError): audit_author_operators(source, 3)


def test_alternative_groups_not_merged_for_training():
    source = fixture(arity=2, fit=False); groups = source['argument_circuits']['groups']
    first = next(iter(groups.values())); alternative = deepcopy(first)
    alternative['premises'] = ['P0']; alternative['premise_occurrences'] = ['NP0']; alternative.pop('id')
    alternative['id'] = fingerprint(alternative); groups[alternative['id']] = alternative
    result = audit_author_operators(source, 3)
    assert sorted(r['arity'] for r in result['rows']) == [1, 2]
    assert all(not r['alternative_groups_merged'] for r in result['rows'])


def test_application_seals_without_model_client_and_preserves_source(tmp_path):
    source = fixture(); inputs = FilePredictionStore(tmp_path / 'in'); output = FilePredictionStore(tmp_path / 'out')
    inputs.seal(source['run_id'], source); app = AuditSealedAuthorOperators(inputs, output)
    a = app.execute(source['run_id'], 3, {'code': 'test'}); b = app.execute(source['run_id'], 3, {'code': 'test'})
    assert a == b and inputs.read_seal(source['run_id']) == source
    assert not a['future_predictions'] and not a['scientific_success'] and not a['graph_advantage_demonstrated']


def test_excluded_source_cannot_enter_training(tmp_path):
    source = fixture(); source['binding']['metadata']['excluded_source_sha256'] = ['a' * 64]
    source['run_id'] = fingerprint(source['binding']); inputs = FilePredictionStore(tmp_path / 'in')
    inputs.seal(source['run_id'], source)
    with pytest.raises(ArticleMapError):
        AuditSealedAuthorOperators(inputs, FilePredictionStore(tmp_path / 'out')).execute(source['run_id'], 3, {})

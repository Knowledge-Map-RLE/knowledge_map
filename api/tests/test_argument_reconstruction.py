"""Проверяет ограниченные операции на реальных frames и контрфактических входах."""
import copy
import importlib.util
import json
import socket
from pathlib import Path

import pytest

from application.argument_reconstruction import run_reconstruction
from domain.argument_reconstruction import reconstruct
from domain.article_maps import ArticleMapError
from infrastructure.immutable_files import write_immutable

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT/'eval/question_prediction/il6-plasma-global-v1/withheld-arguments-engineering-v1/prepare_review.py'
spec = importlib.util.spec_from_file_location('argument_review_fixture', SCRIPT)
fixture = importlib.util.module_from_spec(spec); spec.loader.exec_module(fixture)


@pytest.fixture
def requests():
    return fixture.inputs(fixture.read(fixture.CHAINS/'Jordanova2007/graph.json'),
                          fixture.read(fixture.CHAINS/'TOOTH2016/graph.json'), fixture.read(fixture.TAIWAN/'graph.json'))


def test_real_observations_only_yield_tentative_diagnostic(requests):
    output = reconstruct(requests['Jordanova-J9'])
    assert output['status'] == 'generated' and not output['clinical_forecast'] and not output['causal_identification']
    c = output['conclusions'][0]
    assert c['roles'] == {'exposure': 'IL6', 'outcome': 'DECLINE', 'covariate': 'BMI'}
    assert c['modality'] == 'tentative_diagnostic_hypothesis'
    assert {'exposure_covariate_direction_uncertain', 'identical_analytic_sample_not_verified',
            'odds_ratio_noncollapsibility_not_excluded'} <= set(c['uncertainty'])


@pytest.mark.parametrize('name', ['Jordanova-without-a', 'Jordanova-without-e', 'Jordanova-without-o',
                                 'Jordanova-context-mismatch', 'Jordanova-unit-mismatch', 'Jordanova-alternative-groups',
                                 'Jordanova-negated-input', 'TOOTH-without-validation-condition', 'Taiwan-without-own-result'])
def test_real_premise_ablations_abstain(requests, name):
    assert reconstruct(requests[name])['status'] == 'abstained'


def test_validation_goal_is_not_performed_and_does_not_invent_design(requests):
    c = reconstruct(requests['TOOTH-T8'])['conclusions'][0]
    assert c['action_status'] == 'unresolved' and c['conditions'] == ['before_generalization']
    assert 'longer' not in json.dumps(c) and 'larger' not in json.dumps(c)
    assert c['roles']['intervention'] == 'PREVENTION'


@pytest.mark.parametrize('name', ['TOOTH-T7', 'Taiwan-F3', 'Taiwan-F2'])
def test_use_edges_do_not_supply_causal_or_empirical_rules(requests, name):
    output = reconstruct(requests[name]); assert output['status'] == 'abstained' and output['conclusions'] == []


def test_different_sign_or_other_adjustment_blocks_pattern(requests):
    q = copy.deepcopy(requests['Jordanova-J9'])
    q['facts'][0]['data']['only_added_covariate'] = False
    assert reconstruct(q)['reasons'] == ['other_adjustments_changed']
    q = copy.deepcopy(requests['Jordanova-J9']); d = q['facts'][2]['data']
    d.update(estimate=2.5, ci_lower=.8, ci_upper=4.2)
    assert reconstruct(q)['reasons'] == ['attenuation_pattern_missing']


def test_roles_cannot_be_merged_by_shared_cohort(requests):
    q = copy.deepcopy(requests['Jordanova-J9']); q['facts'][2]['roles']['group'] = 'other_outcome'
    assert reconstruct(q)['reasons'] == ['role_alignment_missing']


@pytest.mark.parametrize('bad_value', [float('nan'), float('inf'), True])
def test_invalid_numbers_fail_closed(requests, bad_value):
    q = copy.deepcopy(requests['Jordanova-J9']); q['facts'][1]['data']['estimate'] = bad_value
    with pytest.raises(ArticleMapError): reconstruct(q)


def test_hidden_text_and_target_payload_are_rejected(requests):
    q = copy.deepcopy(requests['Jordanova-J9']); q['target'] = 'BMI obscures the association'
    with pytest.raises(ArticleMapError): reconstruct(q)
    q = copy.deepcopy(requests['Jordanova-J9']); q['facts'][0]['display_text'] = 'hidden answer'
    with pytest.raises(ArticleMapError): reconstruct(q)


def test_hidden_jordanova_conclusion_and_edge_reasons_do_not_affect_request():
    graphs = [fixture.read(fixture.CHAINS/'Jordanova2007/graph.json'), fixture.read(fixture.CHAINS/'TOOTH2016/graph.json'), fixture.read(fixture.TAIWAN/'graph.json')]
    original = fixture.inputs(*graphs)['Jordanova-J9']
    changed = copy.deepcopy(graphs)
    k = next(k for k in changed[0]['knowledge'] if k['knowledge_id'] == 'J9')
    k['display_text'] = 'unrelated answer'; k['semantic_frame'] = {'logic': 'single', 'statements': []}
    for graph in changed:
        for t in graph['transitions']: t['reason'] = 'unrelated reason'
    assert fixture.inputs(*changed)['Jordanova-J9'] == original
    assert reconstruct(fixture.inputs(*changed)['Jordanova-J9']) == reconstruct(original)


def test_alternative_valid_group_does_not_require_other_group(requests):
    q = copy.deepcopy(requests['TOOTH-T8']); other = copy.deepcopy(q['facts'][0]); other['id'] = 'v2'
    other['negated'] = True; q['facts'].append(other); q['joint_groups'].append(['v2'])
    output = reconstruct(q)
    assert output['status'] == 'generated' and len(output['conclusions']) == 1
    assert output['conclusions'][0]['premises'] == ['v']


def test_application_seals_without_target_network_or_models(requests, monkeypatch):
    def forbidden(*args, **kwargs): raise AssertionError('Network is forbidden')
    monkeypatch.setattr(socket, 'socket', forbidden)
    records = []
    class Store:
        def seal(self, key, value): records.append((key, copy.deepcopy(value)))
    result = run_reconstruction(requests, Store())
    assert [key for key, _ in records] == ['requests.json', 'sealed-output.json']
    assert records[0][1] == requests and records[1][1] == result and result['model_calls'] == 0
    assert not result['training_performed']


def test_sealed_outputs_replay_or_reject_changed_result(requests, tmp_path):
    class Store:
        def seal(self, key, value): write_immutable(tmp_path/key, json.dumps(value, sort_keys=True).encode())
    first = run_reconstruction(requests, Store()); assert run_reconstruction(requests, Store()) == first
    changed = copy.deepcopy(requests); changed['Jordanova-J9']['facts'][1]['data']['estimate'] = .7
    with pytest.raises(ArticleMapError): run_reconstruction(changed, Store())

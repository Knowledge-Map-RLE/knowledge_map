"""Совместимость контекста, независимость семей и разделение стадий."""
from copy import deepcopy
from pathlib import Path
import json
import pytest
from domain.article_maps import fingerprint
from domain.empirical_question_forecast import CONTEXT, ForecastRequest
from domain.guarded_empirical_transfer import transfer, compare_context, verify_record
from application.guarded_empirical_transfer import SealEmpiricalTransfer, EvaluateEmpiricalTransfer
from infrastructure.prepared_transfer_corpus import PreparedTransferCorpus
from infrastructure.empirical_forecast_store import FileEmpiricalForecastStore

ROOT = Path(__file__).resolve().parents[2] / 'eval/question_prediction/il6-plasma-global-v1/guarded-empirical-transfer-v1'


def read(path): return json.loads(path.read_text(encoding='utf-8'))
def corpus(): return PreparedTransferCorpus(read(ROOT / 'prepared-v2/manifest.json'))
def request(): return ForecastRequest.parse(read(ROOT / 'prepared-v2/requests.json')['requests'][0]['request'])
def records(): return read(ROOT / 'prepared-v2/training.json')['records']


def rebound(record):
    value = deepcopy(record)
    obs, evidence = value['observation'], value['semantic_evidence']
    evidence.update(context_sha256=fingerprint(obs['context']), findings_sha256=fingerprint(obs['findings']),
                    frame_sha256=fingerprint(evidence['frame']), source_sha256=obs['binding']['source_sha256'], run_id=obs['binding']['run_id'])
    obs['binding']['claim_sha256'] = fingerprint(evidence)
    return value


def compatible(family, reference):
    value = records()[0]
    value['observation'].update(family=family, reference=reference, context=deepcopy(request().context))
    value['observation']['binding']['source_sha256'] = fingerprint({'synthetic': family})
    return rebound(value)


def test_current_sources_cannot_transport():
    result = transfer(records(), request())
    assert result['status'] == 'abstained' and result['independent_admitted_families'] == []
    assert result['scientific_success'] is False and result['author_dependency_rule_learned'] is False
    assert all(row['comparison']['different'] for row in result['applicability'])
    assert all(row['comparison']['unknown'] for row in result['applicability'])


@pytest.mark.parametrize('field', sorted(CONTEXT))
def test_unknown_never_equals_unknown(field):
    left, right = deepcopy(request().context), deepcopy(request().context)
    left[field] = right[field] = None
    result = compare_context(left, right)
    assert not result['applicable'] and field in [r['field'] for r in result['unknown']]


@pytest.mark.parametrize('field', sorted(CONTEXT))
def test_each_changed_context_blocks_exact_policy(field):
    left, right = deepcopy(request().context), deepcopy(request().context)
    original = left[field]
    left[field] = not original if type(original) is bool else original + 1 if type(original) in (int, float) else 'different-value'
    result = compare_context(left, right)
    assert not result['applicable'] and field in [r['field'] for r in result['different']]


def test_3mse_alias_does_not_merge_mmse():
    left, right = deepcopy(request().context), deepcopy(request().context)
    left['instrument'] = '3MSE'; right['instrument'] = '3ms'
    assert compare_context(left, right)['applicable']
    left['instrument'] = 'mmse'
    assert not compare_context(left, right)['applicable']


def test_two_families_can_emit_hypothesis_with_proof_but_not_success():
    result = transfer([compatible('synthetic-a', 'synthetic-a/1'), compatible('synthetic-b', 'synthetic-b/1')], request())
    assert result['status'] == 'hypothesis' and len(result['independent_admitted_families']) == 2
    assert result['scientific_success'] is False
    assert result['findings']['direction']['support_pattern']['origin'] == 'experimental_evidence_join_not_source_map_transition'


def test_repeated_family_does_not_replace_second_family():
    result = transfer([compatible('synthetic-a', 'synthetic-a/1'), compatible('synthetic-a', 'synthetic-a/2')], request())
    assert result['status'] == 'abstained' and result['findings']['direction']['families'] == 1


def test_same_family_mixed_results_get_one_vote():
    first = compatible('synthetic-a', 'synthetic-a/1')
    second = compatible('synthetic-a', 'synthetic-a/2')
    second['observation']['findings']['direction'] = 'less_decline'; second = rebound(second)
    result = transfer([first, second, compatible('synthetic-b', 'synthetic-b/1')], request())
    a = next(e for e in result['findings']['direction']['evidence'] if e['family'] == 'synthetic-a')
    assert a['votes']['more_decline'] == a['votes']['less_decline'] == .5
    assert sum(a['votes'].values()) == 1


@pytest.mark.parametrize('case', ['future', 'same_day', 'heldout'])
def test_unavailable_or_heldout_source_is_excluded(case):
    value = compatible('synthetic-a', 'synthetic-a/1')
    if case == 'future': value['observation']['available_on'] = '2025-01-01'
    if case == 'same_day': value['observation']['available_on'] = request().as_of
    if case == 'heldout': value['observation']['family'] = request().excluded_families[0]
    result = transfer([value], request())
    assert result['independent_admitted_families'] == []


@pytest.mark.parametrize('case', ['findings', 'frame', 'source', 'run', 'context'])
def test_evidence_bindings_reject_changes(case):
    value = deepcopy(records()[0])
    if case == 'findings': value['observation']['findings']['direction'] = 'less_decline'
    if case == 'frame': value['semantic_evidence']['frame']['statements'][0]['predicate'] = 'causes'
    if case == 'source': value['observation']['binding']['source_sha256'] = 'a' * 64
    if case == 'run': value['observation']['binding']['run_id'] = 'other-run'
    if case == 'context': value['observation']['context']['mci'] = 'absent'
    with pytest.raises(ValueError): verify_record(value)


def test_intended_action_and_negation_are_not_observed_effect_labels():
    value = deepcopy(records()[0]); value['semantic_evidence']['frame']['kind'] = 'action'; value['semantic_evidence']['frame']['action_status'] = 'intended'
    with pytest.raises(ValueError): verify_record(rebound(value))
    value = deepcopy(records()[0]); value['semantic_evidence']['frame']['statements'][0]['negated'] = True
    with pytest.raises(ValueError): verify_record(rebound(value))


def test_split_stages_and_repeat_are_immutable(tmp_path):
    c = corpus(); store = FileEmpiricalForecastStore(tmp_path)
    protocol = {'blind_test': False, 'scientific_success': False}
    sealed = SealEmpiricalTransfer(c, store).execute(protocol)
    assert c.reads == ['training', 'requests']
    assert all(r['modes']['guarded_transport']['status'] == 'abstained' for r in sealed['forecasts'])
    assert SealEmpiricalTransfer(corpus(), store).execute(protocol) == sealed
    e = corpus(); evaluation = EvaluateEmpiricalTransfer(e, store).execute(sealed['run_id'])
    assert e.reads == ['outcomes']
    assert EvaluateEmpiricalTransfer(corpus(), store).execute(sealed['run_id']) == evaluation
    direction = [v for r in evaluation['scores'] for v in r['modes']['frequency'] if v['channel'] == 'direction']
    assert len(direction) == 4 and sum(v['categorical_match'] is True for v in direction) == 1


def test_evaluator_before_seal_reads_no_outcomes(tmp_path):
    c = corpus()
    with pytest.raises(FileNotFoundError): EvaluateEmpiricalTransfer(c, FileEmpiricalForecastStore(tmp_path)).execute('a' * 64)
    assert c.reads == []


def test_requests_have_no_followup_results_or_qualitative_answers():
    value = read(ROOT / 'prepared-v2/requests.json')
    encoded = json.dumps(value)
    assert not any(x in encoded for x in ['"findings"', '"p"', '"beta"', '"hazard ratio"', '"detected_more_decline"', '"less_decline"'])
    assert len(value['requests']) == 4


def test_training_cannot_contain_filtered_target_family(tmp_path):
    c = corpus(); initial = c.training()
    initial['records'][0]['observation']['family'] = request().excluded_families[0]
    class Contaminated:
        def training(self): return initial
        def requests(self): return c.requests()
    with pytest.raises(ValueError, match='target family'):
        SealEmpiricalTransfer(Contaminated(), FileEmpiricalForecastStore(tmp_path)).execute({'blind_test': False, 'scientific_success': False})

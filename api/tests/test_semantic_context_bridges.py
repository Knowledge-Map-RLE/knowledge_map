"""Границы применимости мостов, контрмодели и неизменяемость источников."""
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
import json
import pytest
from domain.article_maps import fingerprint
from domain.empirical_question_forecast import ForecastRequest
from domain.semantic_context_bridges import audit_context, derive_representation, counterexamples, slope
from infrastructure.prepared_bridge_corpus import PreparedBridgeCorpus
from infrastructure.empirical_forecast_store import FileEmpiricalForecastStore
from application.context_bridges import AuditContextBridges, DeriveNumericalRepresentations

ROOT = Path(__file__).resolve().parents[2] / 'eval/question_prediction/il6-plasma-global-v1/context-bridges-v1'
def read(p): return json.loads(p.read_text(encoding='utf-8'))
def contexts(): return read(ROOT / 'prepared/contexts.json')
def cases(): return read(ROOT / 'prepared/mathematical-cases.json')['cases']
def corpus(): return PreparedBridgeCorpus(read(ROOT / 'prepared/manifest.json'))


def test_current_contexts_remove_only_threshold_equality_blockers():
    data = contexts()
    for row in data['requests']:
        request = ForecastRequest.parse(row['request'])
        for source in data['sources']:
            result = audit_context(source, request)
            assert result['strict_blocker_count'] - len(result['representation_blockers']) == 2
            assert {r['field'] for r in result['rows'] if r['status'] == 'eligible_difference'} == {'age_min', 'followup_min'}
            assert not result['representation_compatible'] and not result['empirical_transfer_licensed']
            assert 'mci' in result['representation_blockers']


@pytest.mark.parametrize('field,value', [('age_min', 59), ('followup_min', 1.9), ('specimen', 'serum'), ('timing', 'repeated_measure'), ('dementia_excluded', False)])
def test_question_core_is_not_relaxed(field, value):
    data = contexts(); source = deepcopy(data['sources'][0]); source['context'][field] = value
    source['binding']['context_sha256'] = fingerprint(source['context'])
    result = audit_context(source, ForecastRequest.parse(data['requests'][0]['request']))
    assert result['eligibility_reasons'] and not result['representation_compatible']


def test_identity_of_representation_does_not_license_new_population():
    data = contexts(); source = deepcopy(data['sources'][0]); request = ForecastRequest.parse(data['requests'][0]['request'])
    source['context'] = deepcopy(request.context); source['context']['age_min'] = 70
    source['binding']['context_sha256'] = fingerprint(source['context'])
    result = audit_context(source, request)
    assert result['representation_compatible'] and result['eligibility_reasons'] == []
    assert not result['empirical_transfer_licensed'] and not result['knowledge_equivalence']


def test_half_sd_is_same_analysis_reexpression():
    case = cases()[0]; before = deepcopy(case)
    value = derive_representation(case['effect'], case['mapping'])
    assert Decimal(value['result']['estimate']) == Decimal('0.018')
    assert [Decimal(n) for n in value['result']['ci95']] == [Decimal('-0.015'), Decimal('0.05')]
    assert value['result']['p'] == '0.28' and value['result']['context'] == case['effect']['context']
    assert value['result']['source_binding'] == case['effect']['source_binding']
    assert not value['scientific_prediction'] and not value['empirical_transport']
    assert case == before


@pytest.mark.parametrize('a,c', [('1','2'),('2','1'),('10','2'),('0.1','1'),('1','0.1')])
@pytest.mark.parametrize('point', ['-0.3', '0', '0.3'])
def test_positive_scales_preserve_sign_null_and_interval_membership(a,c,point):
    case = deepcopy(cases()[0]); case['effect'].update(estimate=point, ci95=['-1','1'])
    case['mapping'].update(a=a,c=c)
    output = derive_representation(case['effect'], case['mapping'])['result']
    x = Decimal(point); y = Decimal(output['estimate'])
    assert (x > 0) == (y > 0) and (x < 0) == (y < 0)
    assert Decimal(output['ci95'][0]) <= y <= Decimal(output['ci95'][1])
    assert output['test']['null_value'] == '0' and output['p'] == case['effect']['p']


def test_ratio_reverse_swaps_roles_and_ci_endpoints():
    case = cases()[1]
    output = derive_representation(case['effect'], case['mapping'])['result']
    assert abs(Decimal(output['estimate']) * Decimal('0.94') - 1) < Decimal('1e-26')
    assert Decimal(output['ci95'][0]) < 1 < Decimal(output['ci95'][1])
    assert output['contrast']['numerator'] == case['effect']['contrast']['denominator']
    second = derive_representation(output, case['mapping'])['result']
    assert abs(Decimal(second['estimate']) - Decimal('0.94')) < Decimal('1e-26')
    assert second['contrast'] == case['effect']['contrast'] and second['p'] == case['effect']['p']


@pytest.mark.parametrize('field,value', [('a','0'),('a','-1'),('c','0'),('c','-1'),('a','NaN'),('c','Infinity'),('b','unknown')])
def test_unlicensed_affine_parameters_are_rejected(field,value):
    case = deepcopy(cases()[0]); case['mapping'][field] = value
    with pytest.raises(ValueError): derive_representation(case['effect'],case['mapping'])


@pytest.mark.parametrize('kind', ['linear_to_log','MMSE_to_3MS','slope_to_event','cross_study'])
def test_names_do_not_create_numeric_mapping(kind):
    case = deepcopy(cases()[0]); case['mapping']['kind'] = kind
    with pytest.raises(ValueError): derive_representation(case['effect'],case['mapping'])


def test_analysis_null_and_full_test_cannot_change():
    case = deepcopy(cases()[0]); case['mapping']['analysis_id'] = 'different-study'
    with pytest.raises(ValueError): derive_representation(case['effect'],case['mapping'])
    case = deepcopy(cases()[0]); case['effect']['test']['policy'] = 'refit-new-test'
    with pytest.raises(ValueError): derive_representation(case['effect'],case['mapping'])
    case = deepcopy(cases()[1]); case['effect']['ci95'][0] = '0'
    with pytest.raises(ValueError): derive_representation(case['effect'],case['mapping'])


def test_counterexamples_are_computed_and_not_clinical_refutations():
    examples = {r['id']: r for r in counterexamples()}
    quartile = examples['quartile_to_continuous']; inp = quartile['input']
    assert inp['score_change'][-1] - inp['score_change'][0] < 0 < slope(inp['x'],inp['score_change'])
    log = examples['linear_to_log']['quantities']; assert log['raw_slope'] < 0 < log['log_slope']
    mixture = examples['aggregate_to_MCI_stratum']['quantities']
    assert mixture['within_A_high_minus_low'] < 0 < mixture['pooled_high_minus_low']
    time = examples['average_to_instantaneous']['quantities']; assert time['average_rate_0_to_3'] < 0 < time['instantaneous_rate_at_3_5']
    assert all(r['synthetic'] and r['unconditional_bridge_refuted'] and not r['scientific_article_refuted'] for r in examples.values())


def test_stage_separation_and_immutable_repeat(tmp_path):
    c = corpus(); store = FileEmpiricalForecastStore(tmp_path)
    audit = AuditContextBridges(c,store).execute({'blind_test':False})
    assert c.reads == ['contexts'] and audit['clinical_predictions'] == 0
    assert AuditContextBridges(corpus(),store).execute({'blind_test':False}) == audit
    d = corpus(); derived = DeriveNumericalRepresentations(d,store).execute()
    assert d.reads == ['mathematical_cases'] and len(derived['rows']) == 2
    assert DeriveNumericalRepresentations(corpus(),store).execute() == derived


def test_context_packet_has_no_target_effect_or_numeric_answer():
    encoded = json.dumps(contexts())
    assert not any(key in encoded for key in ['"findings"','"p"','"estimate"','"ci95"','"n"','"beta"','"hr"'])


def test_changed_context_binding_and_future_date_fail():
    data = contexts(); source = deepcopy(data['sources'][0]); source['context']['mci'] = 'absent'
    with pytest.raises(ValueError): audit_context(source,ForecastRequest.parse(data['requests'][0]['request']))
    data['sources'][0]['available_on'] = '2017-01-01'
    class Corrupt:
        def contexts(self):return data
    class Unused:
        def seal(self,*args): raise AssertionError('Must not publish corrupt audit')
    with pytest.raises(ValueError): AuditContextBridges(Corrupt(),Unused()).execute({})

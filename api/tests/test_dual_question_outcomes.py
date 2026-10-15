"""Знак оценки отделён от обнаружимости; аналогия не подтверждает эффект и не подменяет частоту."""
from copy import deepcopy
from dataclasses import replace,asdict
import pytest
from domain.article_maps import ArticleMapError,fingerprint,digest,ArticleMapAccessDenied
from domain.dual_question_outcomes import point_direction,DualOutcomeEngine,validate_transport,transport_scope
from tests.test_qualitative_question_prediction import claim,question,policy,policy_raw,historical
from tests.test_structured_question_context import profiles_for


def transport():
    from domain.dual_question_outcomes import TRANSPORTED
    return {'version':'il6-point-direction-transport-1','kind':'unvalidated_cross_study_hypothesis',
        'minimum_age_years':60,'minimum_protocol_years':2,'min_families':2,'transported_features':TRANSPORTED,
        'confirmatory':False,'scope_ru':'Проверяемая аналогия','scope_en':'Exploratory analogy'}


def profiles(cs):
    p=profiles_for(cs)
    for v in p.values():
        v['normalized']['exposure']['value'].update(specimen='plasma',timing='single_baseline')
        v['normalized']['followup']['value']={'protocol':{'value':'3','unit':'year'}}
    return p


@pytest.mark.parametrize('value,label',[('-.13','positive_association'),('.036','inverse_association'),('0','zero_point_estimate')])
def test_nonsignificant_estimate_sign_is_retained_without_claiming_true_effect(value,label):
    d=point_direction(claim(value=value),policy())
    assert d['label']==label and not d['supported_direction'] and not d['biological_direction_proved']


@pytest.mark.parametrize('value,label',[('1.5','positive_association'),('.94','inverse_association'),('1','zero_point_estimate')])
def test_ratio_uses_reference_one(value,label):
    c=replace(claim(),measurements=({'name':'hazard ratio','value':value,'unit':'dimensionless'},))
    assert point_direction(c,policy())['label']==label


@pytest.mark.parametrize('ci,supported',[([-.47,.21],False),([-.4,-.01],True),([-.2,0],False)])
def test_ci_uncertainty_remains_separate_from_point_sign(ci,supported):
    c=replace(claim(value='-.13',modality='statistically detected' if supported else 'not statistically detected'),measurements=({'name':'beta','value':'-.13','unit':'mmse points/year'},
        {'name':'beta ci','value':ci,'unit':'mmse points/year'}))
    d=point_direction(c,policy());assert d['label']=='positive_association' and d['supported_direction']==supported


def test_nominal_ci_does_not_override_author_multiple_testing_threshold():
    c=replace(claim(value='-.13'),measurements=({'name':'beta','value':'-.13','unit':'mmse points/year'},
        {'name':'beta ci','value':[-.4,-.01],'unit':'mmse points/year'}))
    d=point_direction(c,policy())
    assert d['details'][0]['ci_status']=='excludes_reference' and not d['supported_direction']


def test_missing_conflicting_negated_and_invalid_interval_do_not_invent_direction():
    assert point_direction(replace(claim(),measurements=()),policy())['label'] is None
    assert point_direction(replace(claim(),negated=True),policy())['label'] is None
    c=replace(claim(),measurements=claim().measurements+({'name':'hazard ratio','value':'.5','unit':'dimensionless'},))
    assert point_direction(c,policy())['label'] is None
    c=replace(claim(),measurements=claim().measurements+({'name':'beta ci','value':[2,3],'unit':'mmse points/year'},))
    with pytest.raises(ArticleMapError,match='interval'):point_direction(c,policy())


def test_transport_requires_explicit_anchors_and_exposes_unknown_modifiers():
    p=profiles({('a','K1S1'):claim()})['a','K1S1']['normalized']
    p['mci']={'status':'not_reported','value':None}
    r=transport_scope(p,transport());assert r['eligible'] and 'mci' in r['unknown_features'] and not r['context_equivalence_confirmed']
    p['exposure']['value']['specimen']='serum';assert not transport_scope(p,transport())['eligible']


def test_unvalidated_policy_cannot_claim_confirmation_or_less_than_two_families():
    p=transport();p['confirmatory']=True
    with pytest.raises(ArticleMapError):validate_transport(p)
    p=transport();p['min_families']=1
    with pytest.raises(ArticleMapError):validate_transport(p)


def test_directional_template_is_separate_from_strict_statistical_channel():
    cs,es=historical();ps=profiles(cs)
    for e in es:
        k=tuple(e['conclusion']);cs[k]=replace(cs[k],context={**cs[k].context,'stratum':{'status':'known','value':'another age band'}})
        ps[k]['normalized']['age']['value']['minimum']['value']='85'
        # Обе последующие независимые семьи наблюдают снижение при большем IL-6.
        cs[k]=replace(cs[k],measurements=({'name':'beta','value':'-.2','unit':'mmse points/year'},))
    engine=DualOutcomeEngine(ps,transport());before=[c.to_dict() for c in cs.values()]
    result=engine.fit(cs,es,{},question(),policy());direction=result['outcome_channels']['reported_direction_exploratory']
    assert direction['modes']['semantic'] and not result['modes']['semantic']
    candidate=direction['modes']['semantic'][0]
    assert candidate['support']==2 and candidate['numerical_evidence'] and not candidate['confirmation_eligible']
    assert candidate['status']!='family_majority_baseline' and not direction['modes']['dependency']
    assert [c.to_dict() for c in cs.values()]==before


def test_repeated_heads_in_one_family_do_not_support_directional_rule():
    cs,es=historical()
    for e in es:
        k=tuple(e['conclusion']);cs[k]=replace(cs[k],evidence=replace(cs[k].evidence,family='same'))
    d=DualOutcomeEngine(profiles(cs),transport()).fit(cs,es,{},question(),policy())['outcome_channels']['reported_direction_exploratory']
    assert not d['modes']['semantic']


def test_baseline_abstains_for_conflicted_family_and_never_becomes_semantic_rule():
    a=claim('a','same',value='-.1');b=claim('b','same',value='.2');c=claim('c','other',value='-.1')
    cs={(x.evidence.article_id,x.claim_id):x for x in [a,b,c]}
    d=DualOutcomeEngine(profiles(cs),transport()).fit(cs,[],{},question(),policy())['outcome_channels']['reported_direction_exploratory']
    assert d['ambiguous_families_excluded']==['same'] and not d['modes']['family_frequency_baseline']
    assert not d['modes']['semantic']


def test_all_target_estimates_are_scored_without_cherry_picking_and_ci_truth_is_not_inferred():
    cs,es=historical()
    for e in es:
        k=tuple(e['conclusion']);cs[k]=replace(cs[k],measurements=({'name':'beta','value':'-.1','unit':'mmse points/year'},))
    targets=[claim('target','heldout','2024-01-01',value='-.2'),replace(claim('target','heldout','2024-01-01',value='.2'),claim_id='K2S1')]
    ps=profiles({**cs,**{('target',t.claim_id):t for t in targets}});engine=DualOutcomeEngine(ps,transport())
    result=engine.fit(cs,es,{},question(),policy());result['binding']={'training_families':[]}
    evaluated=engine.evaluate(result,targets)['outcome_channels']['reported_direction_exploratory']['modes']['family_frequency_baseline']
    assert evaluated['scorable_comparisons']==2 and evaluated['agreements']==1 and evaluated['different_signs']==1
    assert evaluated['supported_target_comparisons']==0 and evaluated['point_sign_agreement_rate']==.5
    assert not evaluated['confirmation_eligible']
    with pytest.raises(ArticleMapError,match='leaked'):
        result['binding']={'training_families':['heldout']};engine.evaluate(result,targets)


def test_heldout_profile_and_estimate_are_not_used_in_fit():
    cs,es=historical();target=claim('target','heldout','2024-01-01');p=profiles({**cs,('target',target.claim_id):target})
    a=DualOutcomeEngine(p,transport());r=a.fit(cs,es,{},question(),policy())
    p['target',target.claim_id]['normalized']['mci']={'status':'not_reported','value':None}
    b=DualOutcomeEngine(p,transport());assert a.binding_for(cs)==b.binding_for(cs) and r==b.fit(cs,es,{},question(),policy())


def test_statistical_channel_predicts_detection_without_inheriting_direction():
    cs,es=historical()
    for i,(k,c) in enumerate(cs.items()):
        cs[k]=replace(c,modality='statistically detected',measurements=({'name':'beta','value':'-.1' if i%3 else '.1','unit':'mmse points/year'},
            {'name':'p','value':'.01','unit':'dimensionless'}))
    result=DualOutcomeEngine(profiles(cs),transport()).fit(cs,es,{},question(),policy())
    forecasts=result['outcome_channels']['statistical_detection_strict']['modes']['semantic']
    assert forecasts and all(f['finding']=='statistically_detected' for f in forecasts)


def test_application_seals_before_direction_evaluation_and_checks_owner(tmp_path,monkeypatch):
    from tests.test_question_prediction import Maps,map_fixture,registry,reference
    from application.qualitative_question_prediction import SealQualitativeQuestionExperiment
    from infrastructure.development_prediction_store import FilePredictionStore
    import httpx
    monkeypatch.setattr(httpx.Client,'send',lambda *a,**k:pytest.fail('Model/network call prohibited'))
    a,b=map_fixture('a'),map_fixture('b')
    for m in [a,b]:m['source']['text']+=m['article_id'];m['source']['sha256']=digest(m['source']['text'])
    rs={m['article_id']:{**registry(m,'2010-01-01' if m is a else '2015-01-01'),'family':'family-'+m['article_id']} for m in [a,b]}
    store=FilePredictionStore(tmp_path)
    class Engine(DualOutcomeEngine):
        def evaluate(self,sealed,targets):
            assert store.read_seal(sealed['run_id'])==sealed
            return super().evaluate(sealed,targets)
    scenario=SealQualitativeQuestionExperiment(Maps(a,b),store,Engine({},transport()))
    result=scenario.execute([reference(a),reference(b)],rs,{},[],asdict(question()),policy_raw(),'owner')
    assert not result['readiness']['target_reading_allowed']
    with pytest.raises(ArticleMapAccessDenied):scenario.execute([reference(a),reference(b)],rs,{},[],asdict(question()),policy_raw(),'other')

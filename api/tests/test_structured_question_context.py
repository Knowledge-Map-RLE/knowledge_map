"""Проверки явного контекста, доказательств, переноса и изоляции удержанного семейства."""
from copy import deepcopy
from dataclasses import replace,asdict
import pytest

from domain.article_maps import ArticleMapError,digest,fingerprint,ArticleMapAccessDenied
from domain.structured_question_context import (
    FEATURES,VERSION,canonical_value,normalized_features,compare_features,
    validate_feature_records,StructuredQualitativeEngine,structured_projection)
from domain.research_semantics import context_value as cv
from tests.test_qualitative_question_prediction import question,policy,policy_raw,claim,historical


def features():
    proof=[{'source_id':'x','sha256':digest('🙂x'),'start':0,'end':1,'text':'🙂','offset_encoding':'unicode_code_points'}]
    values={'age':{'minimum':{'value':75,'unit':'year'},'maximum':'unrestricted_by_entry_requirement'},
        'dementia_entry':{'method':'adjudicated','excluded':True},'mci':{'stratum':'absent'},
        'baseline_score':{'instrument':'mmse','minimum':{'value':25,'unit':'mmse_point'}},
        'exposure':{'contrast':'top_quartile','threshold':{'value':2.47,'unit':'pg/ml'}},
        'outcome':{'instrument':'mmse','estimand':'annual_change'},'followup':{'value':36,'unit':'month'},
        'adjustments':['age','gender','education'],'model':{'family':'linear_regression'},
        'alpha':{'value':.05,'unit':'dimensionless'},'sample_size':{'value':328,'unit':'participant'}}
    return {k:{'status':'known','value':values[k],'evidence':deepcopy(proof),'note_ru':'Контроль','note_en':'Control'} for k in FEATURES}


def profiles_for(claims):
    return {k:{'normalized':normalized_features(features()),'record':{'reference':list(k)}} for k in claims}


def test_synonyms_covariate_order_and_review_wording_do_not_change_context():
    a=features();b=deepcopy(a)
    b['adjustments']['value']=['education','sex','age','sex']
    b['followup']['value']={'value':3,'unit':'years'}
    for f in b.values():f['note_ru']='Иная подпись';f['note_en']='Other wording'
    assert normalized_features(a)==normalized_features(b)
    compared=compare_features(normalized_features(a),normalized_features(b))
    assert compared['transfer_authorized'] and not compared['knowledge_equivalence_confirmed']


@pytest.mark.parametrize('quantity,expected',[
    ({'value':36,'unit':'month'},{'value':'3','unit':'year'}),
    ({'value':2.47,'unit':'ng/l'},{'value':'2.47','unit':'pg/ml'}),
    ({'value':.00247,'unit':'ng/ml'},{'value':'2.47','unit':'pg/ml'}),
    ({'value':[.43,1.28],'unit':'ng/l'},{'value':['0.43','1.28'],'unit':'pg/ml'})])
def test_exact_dimensions_and_intervals(quantity,expected):assert canonical_value(quantity)==expected


@pytest.mark.parametrize('value,unit',[(True,'year'),('nan','year'),('inf','year'),('abc','year'),(3,'unknown'),([], 'year')])
def test_invalid_or_unsupported_quantity_is_rejected(value,unit):
    with pytest.raises(ArticleMapError):canonical_value({'value':value,'unit':unit})


@pytest.mark.parametrize('field,value',[
    ('age',{'minimum':{'value':85,'unit':'year'},'maximum':'unrestricted_by_entry_requirement'}),
    ('mci',{'stratum':'present'}),('dementia_entry',{'excluded':True,'method':'self_report'}),
    ('baseline_score',{'instrument':'3mse','minimum':{'value':80,'unit':'3ms_point'}}),
    ('exposure',{'contrast':'per_sd_log_il6'}),('outcome',{'instrument':'mmse','estimand':'decline_event'}),
    ('followup',{'value':7,'unit':'year'}),('adjustments',['age','sex']),
    ('model',{'family':'cox'}),('alpha',{'value':.0025,'unit':'dimensionless'}),
    ('sample_size',{'value':786,'unit':'participant'})])
def test_applicability_differences_are_preserved(field,value):
    a=features();b=deepcopy(a);b[field]['value']=value
    compared=compare_features(normalized_features(a),normalized_features(b))
    assert not compared['transfer_authorized'] and compared['differences'][0]['feature']==field
    assert compared['status']=='different_context'


def test_unknown_equals_unknown_is_not_transfer_and_nested_unknown_is_visible():
    a=features();a['mci'].update(status='not_reported',value=None)
    assert compare_features(normalized_features(a),normalized_features(a))['unknown']==['mci']
    a=features();a['exposure']['value']['assay']={'status':'not_reported','value':None}
    assert compare_features(normalized_features(a),normalized_features(a))['unknown']==['exposure']
    a['exposure']['status']='not_reported'
    with pytest.raises(ArticleMapError,match='presumed'):normalized_features(a)


def registry_fixture():
    c=claim('x');c=replace(c,evidence=replace(c.evidence,source_sha256=digest('🙂x')))
    m={'article_id':'x','run_id':'run-x','source':{'text':'🙂x','sha256':digest('🙂x')},'graph':{}}
    r={'article_id':'x','run_id':'run-x','source_sha256':digest('🙂x'),'graph_sha256':fingerprint({}),
       'claim_id':c.claim_id,'claim_sha256':fingerprint(c.to_dict()),'features':features()}
    return {'version':VERSION,'scope':'primary','author':'Codex','expert_validated':False,'records':[r]}, {('x',c.claim_id):c},{'x':m}


def test_unicode_proof_and_exact_claim_source_graph_binding():
    raw,claims,maps=registry_fixture()
    assert validate_feature_records(raw,claims,maps,'primary')


@pytest.mark.parametrize('changed',['run_id','source_sha256','graph_sha256','claim_sha256','claim_id'])
def test_forged_record_binding_rejected(changed):
    raw,claims,maps=registry_fixture();raw['records'][0][changed]='forged'
    with pytest.raises(ArticleMapError):validate_feature_records(raw,claims,maps,'primary')


def test_changed_source_false_span_duplicate_scope_and_future_support_rejected():
    raw,claims,maps=registry_fixture();maps['x']['source']['text']='changed'
    with pytest.raises(ArticleMapError,match='hash'):validate_feature_records(raw,claims,maps,'primary')
    raw,claims,maps=registry_fixture();raw['records'][0]['features']['age']['evidence'][0]['end']=2
    with pytest.raises(ArticleMapError,match='fragment'):validate_feature_records(raw,claims,maps,'primary')
    raw,claims,maps=registry_fixture();raw['records'].append(deepcopy(raw['records'][0]))
    with pytest.raises(ArticleMapError,match='duplicated'):validate_feature_records(raw,claims,maps,'primary')
    raw,claims,maps=registry_fixture()
    with pytest.raises(ArticleMapError,match='scope'):validate_feature_records(raw,claims,maps,'sensitivity')
    raw['records'][0]['features']['age']['evidence'][0]['source_id']='support'
    support={'id':'support','text':'🙂x','sha256':digest('🙂x'),'available_on':'2025-01-01','training':False}
    with pytest.raises(ArticleMapError,match='future'):validate_feature_records(raw,claims,maps,'primary',[support])


def test_structured_features_recover_real_template_when_literal_wording_differs():
    cs,episodes=historical()
    for e in episodes:
        k=tuple(e['conclusion']);cs[k]=replace(cs[k],context={**cs[k].context,'stratum':cv('different textual wording'),'conditions':cv('covariates described in another order')})
    before=deepcopy([c.to_dict() for c in cs.values()])
    engine=StructuredQualitativeEngine(profiles_for(cs));result=engine.fit(cs,episodes,{},question(),policy())
    assert result['structured_context']['literal_comparison']['mode_counts']['semantic']==0
    assert len(result['modes']['semantic'])==1 and result['rules']['semantic'][0]['support']==2
    assert result['modes']['semantic'][0]['numerical_evidence']
    assert [c.to_dict() for c in cs.values()]==before
    assert result['modes']['dependency']==[]


def test_explicit_unknown_blocks_learning_and_missing_profile_never_falls_back():
    cs,episodes=historical();profiles=profiles_for(cs)
    for p in profiles.values():p['normalized']['mci']={'status':'not_reported','value':None}
    result=StructuredQualitativeEngine(profiles).fit(cs,episodes,{},question(),policy())
    assert not result['modes']['semantic']
    assert 'unknown:mci' in result['diagnostics']['semantic']['rejected'][0]['differences']
    profiles.pop(next(iter(profiles)))
    with pytest.raises(ArticleMapError,match='no lexical fallback'):
        StructuredQualitativeEngine(profiles).fit(cs,episodes,{},question(),policy())


def test_heldout_context_cannot_change_fit_on_earlier_training():
    cs,episodes=historical();target=claim('target','heldout','2024-01-01')
    profiles=profiles_for({**cs,('target',target.claim_id):target})
    first=StructuredQualitativeEngine(profiles);before=first.fit(cs,episodes,{},question(),policy())
    poisoned=deepcopy(profiles);poisoned['target',target.claim_id]['normalized']['sample_size']['value']={'value':'9999','unit':'participant'}
    second=StructuredQualitativeEngine(poisoned)
    assert first.binding_for(cs)==second.binding_for(cs)
    assert before==second.fit(cs,episodes,{},question(),policy())


def test_typed_evaluation_retains_new_numbers_but_abstains_for_unknown_or_different_context():
    cs,episodes=historical();target=claim('target','heldout','2024-01-01',value='0.812345')
    profiles=profiles_for({**cs,('target',target.claim_id):target});engine=StructuredQualitativeEngine(profiles)
    forecast=engine.fit(cs,episodes,{},question(),policy());forecast['binding']={'training_families':[]}
    assert engine.evaluate(forecast,[target])['modes']['semantic']['agreements']==1
    profiles['target',target.claim_id]['normalized']['mci']={'status':'not_reported','value':None}
    result=StructuredQualitativeEngine(profiles).evaluate(forecast,[target])['modes']['semantic']
    assert result['scorable_answers']==0 and result['agreement_at_k']['1'] is None
    profiles['target',target.claim_id]['normalized']['mci']={'status':'known','value':{'stratum':'present'}}
    assert StructuredQualitativeEngine(profiles).evaluate(forecast,[target])['modes']['semantic']['agreements']==0


def test_engine_keeps_registry_binding_when_external_input_mutates():
    cs,episodes=historical();profiles=profiles_for(cs);engine=StructuredQualitativeEngine(profiles)
    before=engine.binding_for(cs)
    profiles[next(iter(profiles))]['normalized']['mci']={'status':'not_reported','value':None}
    assert engine.binding_for(cs)==before
    assert engine.fit(cs,episodes,{},question(),policy())['modes']['semantic']


def test_statistical_disagreement_is_not_a_logical_contradiction():
    cs,episodes=historical();target=claim('target','heldout','2024-01-01',value='-.5',modality='statistically detected')
    engine=StructuredQualitativeEngine(profiles_for({**cs,('target',target.claim_id):target}))
    forecast=engine.fit(cs,episodes,{},question(),policy());forecast['binding']={'training_families':[]}
    result=engine.evaluate(forecast,[target])
    assert result['different_statistical_findings_are_not_logical_contradictions']
    assert result['modes']['semantic']['different_findings']==1


def test_repeated_family_cannot_support_structured_template():
    cs,episodes=historical()
    for e in episodes:
        k=tuple(e['conclusion']);cs[k]=replace(cs[k],evidence=replace(cs[k].evidence,family='same-family'))
    assert not StructuredQualitativeEngine(profiles_for(cs)).fit(cs,episodes,{},question(),policy())['modes']['semantic']


def test_injected_application_still_seals_before_target_evaluation_and_checks_owner(tmp_path,monkeypatch):
    from tests.test_question_prediction import Maps,map_fixture,registry,reference
    from application.qualitative_question_prediction import SealQualitativeQuestionExperiment
    from infrastructure.development_prediction_store import FilePredictionStore
    import httpx
    monkeypatch.setattr(httpx.Client,'send',lambda *a,**kw:pytest.fail('Model/network call prohibited'))
    a,b=map_fixture('a'),map_fixture('b')
    for m in (a,b):m['source']['text']+=m['article_id'];m['source']['sha256']=digest(m['source']['text'])
    metadata={a['article_id']:{**registry(a,'2010-01-01'),'family':'family-a'},b['article_id']:{**registry(b,'2015-01-01'),'family':'family-b'}}
    store=FilePredictionStore(tmp_path)
    class Engine(StructuredQualitativeEngine):
        def evaluate(self,sealed,targets):
            assert store.read_seal(sealed['run_id'])==sealed
            return super().evaluate(sealed,targets)
    scenario=SealQualitativeQuestionExperiment(Maps(a,b),store,Engine({}))
    result=scenario.execute([reference(a),reference(b)],metadata,{},[],asdict(question()),policy_raw(),'owner')
    assert not result['readiness']['target_reading_allowed']
    assert 'scorable_structured_family_time_forecast' in result['readiness']['failed_checks']
    assert scenario.execute([reference(a),reference(b)],metadata,{},[],asdict(question()),policy_raw(),'owner')==result
    with pytest.raises(ArticleMapAccessDenied):scenario.execute([reference(a),reference(b)],metadata,{},[],asdict(question()),policy_raw(),'intruder')

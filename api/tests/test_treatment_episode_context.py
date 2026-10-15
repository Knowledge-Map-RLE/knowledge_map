"""Проверка эпизодов, неизвестных концов и запрета выдавать календарь за эффект."""
from copy import deepcopy
from pathlib import Path
import pytest
from domain.article_maps import ArticleMapError,fingerprint
from domain.treatment_episode_context import expand_schedule,calendar_difference,planned_forecast_window,compile_episodes
from infrastructure.treatment_episode_context import FileEpisodeInputs


@pytest.mark.parametrize('schedule,expected',[
    ({'form':'explicit','points':['1','4','8','12']},['1','4','8','12']),
    ({'form':'periodic','first':'3','last':'13','step':'2'},['3','5','7','9','11','13']),
    ({'form':'periodic','first':'0.1','last':'0.3','step':'0.1'},['0.1','0.2','0.3']),
    ({'form':'explicit','points':['0','1.00']},['0','1'])])
def test_exact_finite_schedule_without_rounding(schedule,expected):
    assert expand_schedule(schedule)==expected


@pytest.mark.parametrize('schedule',[
    {'form':'explicit','points':['1','1']},{'form':'explicit','points':['4','1']},
    {'form':'explicit','points':[]},{'form':'explicit','points':['NaN']},
    {'form':'periodic','first':'3','last':'12','step':'2'},
    {'form':'periodic','first':'3','last':'13','step':'0'},
    {'form':'periodic','first':'3','last':'300','step':'1'},
    {'form':'unknown','first':'3','last':'13','step':'2'}])
def test_uncertain_unordered_or_unbounded_schedule_rejected(schedule):
    with pytest.raises(ArticleMapError):expand_schedule(schedule)


def context():
    return{'article_id':'source','case_id':'case','procedure':'clinical','anchor':'post_immunization','unit':'day'}


def test_calendar_difference_is_exact_and_is_not_an_effect_duration():
    r=calendar_difference({'context':context(),'day':'30'},{'context':context(),'day':'16'})
    assert r['difference_days']=='14' and not r['effect_duration_inferred'] and not r['is_new_empirical_prediction']


@pytest.mark.parametrize('field,value',[
    ('anchor','manifest_disease_day'),('article_id','different'),('procedure','tissue'),('case_id','another course')])
def test_different_clocks_episodes_studies_do_not_subtract(field,value):
    altered=context();altered[field]=value
    with pytest.raises(ArticleMapError):calendar_difference({'context':altered,'day':'30'},{'context':context(),'day':'16'})


@pytest.mark.parametrize('purpose,end,origin',[
    ('clinical_followup',None,'unknown'),('clinical_followup','20','axis_upper_tick'),
    ('clinical_followup','18','source_result_assessment'),('tissue_sampling','16','source_method_endpoint')])
def test_outcome_or_tissue_endpoint_is_not_a_forecast_method_window(purpose,end,origin):
    e={'purpose':purpose,'observation_end':end,'observation_end_origin':origin}
    assert planned_forecast_window(e)is None


def test_clinical_method_window_uses_weak_existential_quantifier():
    e={'purpose':'clinical_followup','observation_end':'30','observation_end_origin':'source_method_endpoint',
        'schedule':{'form':'explicit','points':['8','12','16']},'anchor':'post_immunization'}
    r=planned_forecast_window(e)
    assert r['start']=='8' and r['end']=='30' and r['time_quantifier']=='some_assessed_time'
    assert not r['all_times_effect_inferred'] and not r['future_duration_copied_from_result']


@pytest.fixture(scope='module')
def corpus():
    root=Path(__file__).resolve().parents[2]/'eval'/'whole_map_forecast'
    return FileEpisodeInputs(root/'functional-target-guard-v1'/'runs'/'88dea2a6b02bbd7975afdec19e28a31433cd9b690e2fec46f1ca074d18791aa2',
        root/'treatment-episodes-v1'/'prepared-v2'/'audit.json').load()


def test_real_timelines_keep_all_source_constraints_and_inconsistencies(corpus):
    before=fingerprint(corpus[:-1]);r=compile_episodes(*corpus)
    assert fingerprint(corpus[:-1])==before
    assert r['canonical_blocks']==943 and r['semantic_statements']==1897 and r['input_parts']==915
    assert len(r['episodes'])==3 and len(r['calendar_consequences'])==4
    assert sorted(c['difference_days']for c in r['calendar_consequences'])==['14','3','4','6']
    assert len(r['calendar_conflicts'])==len(r['protocol_conflicts'])==1
    assert r['calendar_conflicts'][0]['reported_days']=='12' and r['calendar_conflicts'][0]['computed_days']=='14'
    atros=next(e for e in r['episodes']if e['case_id']=='atrosimab-manifest')
    assert atros['unknown_clinical_observation_end'] and atros['planned_forecast_window']is None
    assert atros['entry']['figure_assessment']['confirmed_assessment_day']=='18'
    assert atros['entry']['figure_assessment']['axis_upper_tick']=='20'
    assert not atros['entry']['figure_assessment']['last_assessment_established']
    assert not r['graph_advantage_demonstrated'] and r['new_empirical_forecasts']==0 and r['eligible_window_families']==0


@pytest.mark.parametrize('change',['swapped_episode','wrong_clock','changed_endpoint','axis_end','omit_figure',
    'drop_conflict','effect_duration','participants','quote','alter_asset','claimed_significance',
    'omit_reported_distance','replace_asset_and_hash'])
def test_source_endpoint_participant_or_effect_forgery_rejected(corpus,change):
    functional,frozen,maps,cases,base,original_assets=corpus;a=deepcopy(base);assets=dict(original_assets)
    clinical=next(e for e in a['entries']if e['case_id']=='tros-manifest')
    atros=next(e for e in a['entries']if e['case_id']=='atrosimab-manifest')
    if change=='swapped_episode':clinical['episodes'][0]['schedule']['points']=['8','12']
    elif change=='wrong_clock':atros['episodes'][0]['anchor']='post_immunization'
    elif change=='changed_endpoint':clinical['episodes'][0]['observation_end']='16'
    elif change=='axis_end':atros['episodes'][0].update(observation_end='20',observation_end_origin='source_method_endpoint')
    elif change=='omit_figure':atros['figure_assessment']=None
    elif change=='drop_conflict':next(e for e in a['entries']if e['case_id']=='tros-prophylactic')['dose_frequency_conflict']=False
    elif change=='effect_duration':clinical['episodes'][0]['source_asserted_effect_duration']='14 days of durable protection'
    elif change=='participants':atros['participants']['population']='all mice'
    elif change=='quote':clinical['evidence'][0]['text']+='!'
    elif change=='alter_asset':assets['atrosimab_figure7']+=b'!'
    elif change=='omit_reported_distance':clinical['reported_after_last_dose_days']=None
    elif change=='replace_asset_and_hash':
        from hashlib import sha256
        assets['atrosimab_figure7']=b'different graph';a['assets']['atrosimab_figure7']['sha256']=sha256(assets['atrosimab_figure7']).hexdigest()
    else:atros['figure_assessment']['pointwise_significance_inferred']=True
    with pytest.raises(ArticleMapError):compile_episodes(functional,frozen,maps,cases,a,assets)


def test_publication_is_reused_and_invalid_revision_cannot_damage_a_seal(corpus,tmp_path):
    from application.treatment_episode_context import SealTreatmentEpisodes
    from infrastructure.development_prediction_store import FilePredictionStore
    class Inputs:
        def __init__(self,data):self.data=data
        def load(self):return self.data
    inputs=Inputs(corpus);store=FilePredictionStore(tmp_path/'runs');service=SealTreatmentEpisodes(inputs,store)
    first=service.execute({});path=store.path(first['run_id'])/'predictions.json';original=path.read_bytes()
    assert service.execute({})==first and path.read_bytes()==original
    bad=list(corpus);bad[-2]=deepcopy(bad[-2]);bad[-2]['entries'][0]['participants']['intervention']='different drug';inputs.data=tuple(bad)
    with pytest.raises(ArticleMapError):service.execute({})
    assert path.read_bytes()==original and len(list((tmp_path/'runs').glob('*/seal.json')))==1

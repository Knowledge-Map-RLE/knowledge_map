"""Наблюдательная эквивалентность, цензурирование и воспроизводимость аудита."""
from copy import deepcopy
from fractions import Fraction
import json
from pathlib import Path
import pytest
from domain.article_maps import ArticleMapError,fingerprint
from domain.observation_identifiability import observe,durations,number,identifiability_witnesses,audit_catalog
from application.observation_identifiability import AuditObservationData
from infrastructure.observation_identifiability import FileObservationInputs,FileObservationAuditStore

ROOT=Path(__file__).resolve().parents[2]/'eval/free_prediction/observation-identifiability-v1'
def read(name):return json.loads((ROOT/'prepared'/name).read_text(encoding='utf-8'))

@pytest.mark.parametrize('value',['NaN','inf','1/0','bad',None,1])
def test_exact_time_required(value):
    with pytest.raises(ArticleMapError):number(value)

def test_endpoint_states_respect_half_open_episode():
    assert observe([{'start':'1','end':'2'}],['0','1','2'])==['normal','MCI','normal']

@pytest.mark.parametrize('episodes',[
    [{'start':'2','end':'1'}],[{'start':'1','end':'1'}],
    [{'start':'0','end':'2'},{'start':'1','end':'3'}],
    [{'start':'0','end':'1'},{'start':'1','end':'2'}]])
def test_invalid_or_unseparated_episodes_rejected(episodes):
    with pytest.raises(ArticleMapError):observe(episodes,['0','2'])

@pytest.mark.parametrize('visits',[[],['2','0'],['0','0']])
def test_visits_order_and_uniqueness_required(visits):
    with pytest.raises(ArticleMapError):observe([],visits)

def test_same_observations_do_not_identify_duration_or_episode_count():
    w=identifiability_witnesses();histories=w['histories']
    assert histories[0]['visit_states']==histories[1]['visit_states']==histories[2]['visit_states']
    assert histories[0]['durations']==['1/5'] and histories[1]['durations']==['24/5']
    assert len(histories[2]['episodes'])==2
    assert w['episode_duration_identified'] is False and w['single_episode_identified'] is False
    assert w['synthetic'] and not w['clinical_estimates']

def test_opposite_education_duration_orders_fit_same_visited_states():
    w=identifiability_witnesses();index={h['id']:h for h in w['histories']}
    orders=[]
    for world in w['education_worlds']:
        high,low=index[world['higher_education']],index[world['lower_education']]
        assert high['visit_states']==low['visit_states']
        orders.append(Fraction(high['durations'][0])>Fraction(low['durations'][0]))
    assert orders==[True,False]

@pytest.mark.parametrize('epsilon',['1/10','1/100','1/1000000'])
def test_no_positive_lower_or_attainable_five_year_upper_bound(epsilon):
    e=Fraction(epsilon)
    for episode in [{'start':str(2-e),'end':str(2+e)},{'start':str(e),'end':str(5-e)}]:
        assert observe([episode],['0','2','5'])==['normal','MCI','normal']
        d=Fraction(durations([episode])[0]);assert 0<d<5

def test_baseline_mci_is_left_censored_not_duration_at_most_two_years():
    w=identifiability_witnesses();a,b=w['baseline_histories']
    assert a['visit_states']==b['visit_states']==['MCI','normal','normal']
    assert a['durations']==['2'] and b['durations']==['101']
    assert w['bounds_under_one_perfectly_observed_contiguous_episode']['baseline_mci_then_normal_total_duration']['finite_upper_bound'] is None

def test_visit_state_retention_is_not_continuous_episode_survival():
    continuous=[{'start':'-1','end':'3'}]
    separate=[{'start':'-1','end':'1'},{'start':'3/2','end':'3'}]
    assert observe(continuous,['0','2','5'])==observe(separate,['0','2','5'])
    assert len(continuous)!=len(separate)

def test_source_schedules_do_not_become_measured_episode_durations():
    result=audit_catalog(read('catalog.json'));rows={r['source_id']:r for r in result['sources']}
    assert rows['larrieu2002']['nominal_intervals_years']==['2','3']
    assert rows['larrieu2002']['nominal_regular'] is False
    assert rows['katz2012']['nominal_regular'] is True
    assert rows['manly2008']['nominal_regular'] is None
    assert all(not r['duration_order_established'] and not r['ready_for_empirical_interval_effect_test'] for r in rows.values())
    assert result['scientific_success'] is False

def test_table_estimand_cannot_be_silently_replaced_by_duration():
    c=read('catalog.json');c['paquid_table']['estimand']='episode_duration'
    with pytest.raises(ArticleMapError):audit_catalog(c)

def test_printed_percentages_and_explicit_counts_preserved():
    table=audit_catalog(read('catalog.json'))['paquid_table']
    assert table['rows'][0]['initial_n']==58 and table['rows'][0]['percent']['MCI']=='6.9'
    assert table['rows'][1]['initial_n']==37 and table['rows'][1]['percent']['MCI']=='5.4'
    assert table['rows'][1]['percent']['missing_and_withdrawals']=='2.9'
    assert table['explicit_counts_in_prose'][0]['next_MCI']==4
    assert table['education_stratified'] is False

def test_registered_sources_unicode_and_prior_result_verified():
    port=FileObservationInputs(ROOT/'prepared/manifest.json');data=port.read_inputs()
    assert len(data['evidence']['sources'])==7 and len(data['evidence']['fragments'])==12
    assert all('hidden-profiles' not in p and 'PMC10000452' not in p for p in port.reads)

def test_idempotent_audit_recovers_after_unsealed_partial_write(tmp_path):
    port=FileObservationInputs(ROOT/'prepared/manifest.json');store=FileObservationAuditStore(tmp_path)
    usecase=AuditObservationData(port,store);first=usecase.execute({'code':'frozen'})
    assert first==usecase.execute({'code':'frozen'})
    folder=store.path(first['run_id']);(folder/'seal.json').unlink()
    assert store.read(first['run_id']) is None
    assert first==usecase.execute({'code':'frozen'})

def test_immutable_audit_cannot_be_replaced(tmp_path):
    store=FileObservationAuditStore(tmp_path);first=AuditObservationData(FileObservationInputs(ROOT/'prepared/manifest.json'),store).execute({})
    changed=deepcopy(first);changed['audit']['empirical_predictions']=1
    with pytest.raises(ArticleMapError):store.save(first['run_id'],changed)
    assert store.read(first['run_id'])==first

def test_changed_implementation_creates_another_record(tmp_path):
    usecase=AuditObservationData(FileObservationInputs(ROOT/'prepared/manifest.json'),FileObservationAuditStore(tmp_path))
    a=usecase.execute({'code':'a'});b=usecase.execute({'code':'b'})
    assert a['run_id']!=b['run_id'] and a['audit']==b['audit']

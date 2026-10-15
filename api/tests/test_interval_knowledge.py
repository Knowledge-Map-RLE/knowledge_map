"""Геометрия, совместное покрытие и происхождение не подменяются клиническим тестом."""
from copy import deepcopy
from decimal import Decimal
from hashlib import sha256
import pytest
from domain.article_maps import ArticleMapError, fingerprint
from domain.interval_knowledge import geometry, coverage_bound, compile_entries, analyze, VERSION
from domain.semantic_part_forecast import forecast_parts
from domain.typed_participant_forecast import forecast as typed_forecast
from tests.test_semantic_part_forecast import prepare
from tests.test_whole_map_forecast import corpus, families


@pytest.mark.parametrize('left,right,expected', [(['7.241','11.09'],['5.366','7.884'],['-0.643','5.724']),
    (['7.55','10.65'],['6.03','7.69'],['-0.14','4.62']), (['1','1'],['3','3'],['-2','-2']),
    (['0.1','0.3'],['0.2','0.4'],['-0.3','0.1'])])
def test_exact_interval_difference_and_every_rectangle_corner(left, right, expected):
    result = geometry(left, right); assert result['difference'] == expected
    low, high = map(Decimal, expected)
    for x in map(Decimal, left):
        for y in map(Decimal, right): assert low <= x-y <= high
    assert not result['effect_absence_inferred'] and not result['statistical_detection_inferred']


@pytest.mark.parametrize('a,b', [(['NaN','1'],['0','1']), (['1','0'],['0','1']), ([0,'1'],['0','1']),
    (['0','Infinity'],['0','1']), (['0','1','2'],['0','1'])])
def test_invalid_interval_is_rejected(a,b):
    with pytest.raises(ArticleMapError): geometry(a,b)


def test_decimal_arithmetic_remains_exact_beyond_default_decimal_precision():
    x='1'+'0'*40; expected='9'*40
    assert geometry([x,x],['1','1'])['difference']==[expected,expected]
    assert coverage_bound('99.'+'9'*35,'95')['conditional_joint_coverage_percent_at_least']=='94.'+'9'*35
    for value in ['1_000','1e999999']:
        with pytest.raises(ArticleMapError): geometry([value,value],['1','1'])


def test_overlap_does_not_establish_null_effect_or_lack_of_detection():
    assert geometry(['7.241','11.09'],['5.366','7.884'])['overlap']
    assert geometry(['7.55','10.65'],['6.03','7.69'])['overlap']
    for bounds in [(['0','1'],['1','2']), (['2','3'],['0','1'])]:
        r = geometry(*bounds); assert not r['statistical_detection_inferred'] and not r['effect_absence_inferred']


def test_nominal_95_plus_95_does_not_become_95_joint_or_parameter_probability():
    r = coverage_bound('95', '95'); assert r['conditional_joint_coverage_percent_at_least'] == '90'
    assert not r['assumed_independence'] and not r['parameter_probability_asserted']
    assert not r['actual_coverage_verified'] and not r['reported_rounded_bounds_coverage_verified']
    assert coverage_bound('20','30')['conditional_joint_coverage_percent_at_least'] == '0'


def test_joint_lower_bound_is_sharp_under_unknown_dependence():
    # Перебор всех распределений двух событий на сетке 1/20, включая зависимые случаи.
    joint = []
    for both in range(21):
        for first_only in range(21-both):
            for second_only in range(21-both-first_only):
                pa, pb = both+first_only, both+second_only
                bound = max(0, pa+pb-20)
                assert both >= bound
                if pa >= 19 and pb >= 19: joint.append(both)
    assert min(joint) == 18 and max(joint) == 20


@pytest.mark.parametrize('left,right', [('0','95'),('101','95'),('95','-1'),('NaN','95')])
def test_invalid_confidence_coefficient_rejected(left,right):
    with pytest.raises(ArticleMapError): coverage_bound(left,right)


def inputs():
    maps = corpus(); k = maps[0]['graph']['knowledge'][2]; s = k['semantic_frame']['statements'][0]
    s['predicate'] = 'onset_delayed_after_intervention'
    s['qualifiers']['attributes'] = [{'name': 'tros_onset_ci_lower','value': '7.241','unit':'day'},
        {'name':'tros_onset_ci_upper','value':'11.09','unit':'day'}, {'name':'pbs_onset_ci_lower','value':'5.366','unit':'day'},
        {'name':'pbs_onset_ci_upper','value':'7.884','unit':'day'}, {'name':'CI_level','value':'95','unit':'percent'}]
    maps, origins = prepare(maps)
    text = 'We observed a significant delay (95% CI 7.241–11.09 vs. 5.366–7.884 days, respectively).'
    m = maps[0]; m['source']['text'] = text; m['source']['content_end'] = len(text); m['source']['sha256'] = sha256(text.encode()).hexdigest()
    m['source']['units'] = [{'id':'U1','start':0,'end':len(text),'text':text}]
    origin = origins['sources'][0]; origin['source_sha256'] = m['source']['sha256']
    q = {**m['source']['units'][0], 'unit_id':'U1','sha256':sha256(text.encode()).hexdigest()}; origin['evidence'] = [q]
    frozen = forecast_parts(maps, families(maps), None, None, origins)
    frozen['binding'] = {'map_hashes':[fingerprint(m) for m in maps], 'families':families(maps)}; frozen['run_id'] = fingerprint(frozen['binding'])
    baseline = typed_forecast(frozen,maps,origins); baseline['binding'] = {'source_sha256':fingerprint(frozen)}
    baseline['run_id'] = fingerprint(baseline['binding'])
    audit = {'version':VERSION,'author':'Codex','model_calls':0,'expert_validated':False,'input_sha256':fingerprint(frozen),
        'map_hashes':[fingerprint(m) for m in maps], 'entries':[{'native_key':[m['article_id'],k['knowledge_id']],
        'statement_id':s['statement_id'],'run_id':m['run_id'],'source_sha256':m['source']['sha256'],'knowledge_sha256':fingerprint(k),
        'estimand_ru':'Средний день начала симптомов.','clock_ru':'Дни в одном опыте.','reason_ru':'Синтетический тест.',
        'level_field':'ci level','unit':'day','reported_detection':'detected','evidence':[q],
        'intervals':[{'label_ru':'Первая группа','lower_field':'tros onset ci lower','upper_field':'tros onset ci upper'},
                     {'label_ru':'Контроль','lower_field':'pbs onset ci lower','upper_field':'pbs onset ci upper'}]}]}
    return baseline,frozen,maps,origins,audit


def test_projection_retains_complete_parent_scope_roles_and_source_numbers():
    baseline,frozen,maps,origins,audit = inputs(); before=deepcopy((baseline,frozen,maps,origins,audit))
    consequences, changes, _ = compile_entries(frozen,maps,origins,audit)
    assert len(consequences) == len(changes) == 1
    c=consequences[0]; assert c['geometry']['difference']==['-0.643','5.724'] and c['reported_detection']=='detected'
    assert not c['future_prediction'] and not c['scientific_confirmation']
    v=next(iter(changes.values())); p=v['projection_proof']; old=p['interval_summary_proof']['complete_input_frame']
    assert len(p['interval_summary_proof']['removed_summary_fields'])==5
    assert v['frame']['statements'][0]['attributes']==[a for a in old['statements'][0]['attributes']
        if a['name'] not in p['interval_summary_proof']['removed_summary_fields']]
    for name in ('roles','scope','predicate','negated'): assert old['statements'][0][name]==v['frame']['statements'][0][name]
    assert p['complete_native_knowledge']==maps[0]['graph']['knowledge'][2]
    assert (baseline,frozen,maps,origins,audit)==before


@pytest.mark.parametrize('case',['quote','unit','status','source','level','parent','origin','duplicate'])
def test_forged_or_incompatible_license_rejected(case):
    _,frozen,maps,origins,audit=inputs(); e=audit['entries'][0]
    if case=='quote': e['evidence'][0]['text']+='!'
    elif case=='unit': e['unit']='hour'
    elif case=='status': e['reported_detection']='not_detected'
    elif case=='source': e['source_sha256']='0'*64
    elif case=='level': e['level_field']='tros onset ci lower'
    elif case=='parent': e['knowledge_sha256']='0'*64
    elif case=='origin': origins['sources'][0]['knowledge'][2]['statements'][0]['origin']='cited_result'
    else: audit['entries'].append(deepcopy(e))
    with pytest.raises(ArticleMapError): compile_entries(frozen,maps,origins,audit)


def test_complete_paired_run_uses_same_corpus_and_never_confuses_deduction_with_forecast(monkeypatch):
    import socket
    monkeypatch.setattr(socket,'create_connection',lambda *a,**k: pytest.fail('Network/model forbidden'))
    baseline,frozen,maps,origins,audit=inputs(); r=analyze(baseline,frozen,maps,origins,audit)
    assert r['canonical_blocks']==len(r['coverage'])==8 and r['licensed_parts']==8
    assert r['baseline_learning_reproduced'] and not r['scientific_success'] and not r['graph_advantage_demonstrated']
    assert r['model_calls']==0 and not r['target_read'] and len(r['interval_consequences'])==1


def test_immutable_application_reuses_success_and_keeps_old_run_on_failed_source(tmp_path):
    from application.interval_knowledge import SealIntervalKnowledge
    from infrastructure.development_prediction_store import FilePredictionStore
    values=inputs()
    class Port:
        def load(self): return values
    store=FilePredictionStore(tmp_path); app=SealIntervalKnowledge(Port(),store)
    first=app.execute({'test':'first'}); assert first==app.execute({'test':'first'})
    values[-1]['entries'][0]['source_sha256']='0'*64
    with pytest.raises(ArticleMapError): app.execute({'test':'first'})
    assert store.read_seal(first['run_id'])==first and len(list(tmp_path.glob('*/seal.json')))==1

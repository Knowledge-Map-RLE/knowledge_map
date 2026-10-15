"""Смена начала отсчёта сохраняет расстояния и не разрешает перенос чужих условий."""
from copy import deepcopy
from decimal import Decimal
from itertools import combinations
from pathlib import Path
import pytest
from domain.article_maps import ArticleMapError,fingerprint
from domain.first_administration_clock import reference,relative_point,restore_point,bind_relative_parameter,analyze_clocks
from infrastructure.first_administration_clock import FileClockInputs


def source_context():
    return{'article_id':'article','case_id':'case','procedure':'clinical','anchor':'post_immunization','unit':'day'}


@pytest.mark.parametrize('first,point,expected',[
    ('8','8','0'),('8','12','4'),('8','30','22'),('1','18','17'),('3','0','-3'),
    ('0.100001','0.100002','0.000001'),('999999999999.999998','999999999999.999999','0.000001')])
def test_exact_source_coordinates_and_reversible_negative_offsets(first,point,expected):
    c=source_context();ref=reference(c,first);p=relative_point({'context':c,'day':point},ref)
    assert p['value']==expected and restore_point(p,ref)=={'context':c,'day':point}


def test_generated_affine_order_and_distance_invariants():
    # Все пары из разных календарей; проверяется закон преобразования, а не число примеров.
    c=source_context();points=['0','0.01','1','3','8','12','16','30','100']
    for first in ['0','0.02','3','8','100']:
        ref=reference(c,first);out={v:relative_point({'context':c,'day':v},ref)for v in points}
        for a,b in combinations(points,2):
            left,right=Decimal(out[a]['value']),Decimal(out[b]['value'])
            assert right-left==Decimal(b)-Decimal(a) and left<right
        for v in points:assert restore_point(out[v],ref)=={'context':c,'day':v}


@pytest.mark.parametrize('field,value',[
    ('article_id','another article'),('case_id','another course'),('procedure','tissue'),
    ('anchor','manifest_disease_day'),('unit','week')])
def test_foreign_context_cannot_be_bound_even_if_numbers_match(field,value):
    c=source_context();ref=reference(c,'8');other={**c,field:value}
    with pytest.raises(ArticleMapError):relative_point({'context':other,'day':'12'},ref)


@pytest.mark.parametrize('change',['wrong_id','changed_origin','invalid_value','wrong_unit','negative_restore','oversized_restore'])
def test_corrupt_reference_or_coordinate_rejected(change):
    c=source_context();ref=reference(c,'8');p=relative_point({'context':c,'day':'12'},ref)
    if change=='wrong_id':p['reference_id']='another'
    elif change=='changed_origin':ref['first_dose_day']='12'
    elif change=='invalid_value':p['value']='Infinity'
    elif change=='wrong_unit':p['unit']='hour'
    elif change=='negative_restore':p['value']='-9'
    else:p['value']='1000000000000'
    with pytest.raises(ArticleMapError):restore_point(p,ref)


def test_plot_point_cannot_fill_method_slot_or_become_effect_duration():
    c=source_context();ref=reference(c,'1');p={'point':{'context':c,'day':'18'},'source_origin':'source_result_plot'}
    with pytest.raises(ArticleMapError):bind_relative_parameter(p,ref,{'source_method_endpoint'})
    bound=bind_relative_parameter(p,ref,{'source_result_plot'})
    assert bound['point']['value']=='17' and not bound['new_effect_duration_inferred']


@pytest.fixture(scope='module')
def corpus():
    root=Path(__file__).resolve().parents[2]/'eval'/'whole_map_forecast'
    return FileClockInputs(root/'treatment-episodes-v1'/'runs'/'de6efef9e3583d16509a253e91b436f3afd7149a990ef1c12f9411cc6cd432f3').load()


def test_actual_source_transform_keeps_unknown_ends_doses_and_disagreements(corpus):
    before=fingerprint(corpus);r=analyze_clocks(corpus);assert fingerprint(corpus)==before
    assert len(r['clock_proofs'])==4 and len({p['reference']['id']for p in r['clock_proofs']})==4
    curves={p['procedure']:p for p in r['clock_proofs']}
    def points(name):return[x['point']['value']for x in curves[name]['relative_doses']]
    assert points('prophylactic_clinical')==['0','2','4','6','8','10']
    assert points('therapeutic_clinical')==['0','4','8'] and points('therapeutic_tissue')==['0','4']
    assert points('manifest_clinical')==['0','3','7','11']
    assert curves['prophylactic_clinical']['relative_endpoint']['point']['value']=='13'
    assert curves['therapeutic_clinical']['relative_endpoint']['point']['value']=='22'
    assert curves['therapeutic_tissue']['relative_endpoint']['point']['value']=='8'
    assert curves['manifest_clinical']['relative_endpoint']is None and curves['manifest_clinical']['relative_method_window']is None
    assert curves['manifest_clinical']['relative_graphical_points'][0]['point']['value']=='17'
    assert r['source_calendar_conflicts']==corpus['calendar_conflicts'] and r['source_protocol_conflicts']==corpus['protocol_conflicts']
    assert r['source_guarded_prototype']==corpus['guarded_prototype']
    assert r['source_temporal_relations']==r['normalized_temporal_relations']
    assert all(not p['same_reference_type']or not p['experimental_equivalence']for p in r['comparisons'])
    assert r['new_empirical_forecasts']==0 and not r['scientific_success'] and not r['graph_advantage_demonstrated']
    assert not r['empirical_generator_run']


def test_intended_or_unfinished_actions_cannot_supply_performed_episode(corpus):
    bad=deepcopy(corpus);bad['episodes'][0]['complete_case']['method']['frame']['action_status']='planned'
    with pytest.raises(ArticleMapError):analyze_clocks(bad)


def test_first_dose_zero_allows_both_coinciding_and_earlier_disease_onset(corpus):
    c=source_context();ref=reference(c,'8')
    assert relative_point({'context':c,'day':'8'},ref)['value']=='0'
    assert [relative_point({'context':c,'day':onset},ref)['value']for onset in ['6','8']]==['-2','0']
    # Обе контрмодели сохраняют первое введение в нуле; календарь не решает вопрос тождества событий.
    for p in analyze_clocks(corpus)['clock_proofs']:
        assert p['biological_onset_equivalence_inferred']is False
        assert 'first_dose_is_not_biological_onset'not in p


def test_seal_reuse_and_invalid_revision_preserve_the_old_result(corpus,tmp_path):
    from application.first_administration_clock import SealFirstAdministrationClock
    from infrastructure.development_prediction_store import FilePredictionStore
    class Inputs:
        def __init__(self,data):self.data=data
        def load(self):return self.data
    inputs=Inputs(corpus);store=FilePredictionStore(tmp_path/'runs');service=SealFirstAdministrationClock(inputs,store)
    first=service.execute({});path=store.path(first['run_id'])/'predictions.json';original=path.read_bytes()
    assert service.execute({})==first and path.read_bytes()==original
    bad=deepcopy(corpus);bad['episodes'][0]['complete_case']['method']['frame']['action_status']='planned';inputs.data=bad
    with pytest.raises(ArticleMapError):service.execute({})
    assert path.read_bytes()==original and len(list((tmp_path/'runs').glob('*/seal.json')))==1

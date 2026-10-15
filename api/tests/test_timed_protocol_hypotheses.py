"""Новые сочетания сохраняют гипотетический статус и не получают исходы из будущей статьи."""
from copy import deepcopy
from pathlib import Path
import pytest
from domain.article_maps import ArticleMapError,fingerprint,require
from domain.timed_protocol_hypotheses import forecast,combine
from infrastructure.timed_protocol_hypotheses import FileTimedHypothesisInputs


@pytest.fixture(scope='module')
def corpus():
    return FileTimedHypothesisInputs(Path(__file__).resolve().parents[2]/'eval'/'whole_map_forecast'/
        'timed-clinical-source-review-v1'/'review-v1').load()


def test_real_free_generation_keeps_full_corpus_and_does_not_claim_graph_advantage(corpus):
    before=fingerprint(corpus);r=forecast(*corpus);assert fingerprint(corpus)==before
    assert r['question']is None and r['canonical_blocks']==943 and r['semantic_statements']==1897
    assert len(r['input_inventory'])==943 and r['licensed_source_cases']==2 and not r['operator_coverage_is_whole_corpus']
    assert r['candidate_count']==3 and len(r['modes']['same_facts_without_dependencies'])==3
    assert {p['id']for p in r['modes']['graph']}=={p['id']for p in r['modes']['same_facts_without_dependencies']}
    for proposal in r['modes']['graph']:
        assert proposal['body'][1]['action_status']==proposal['body'][2]['action_status']=='planned'
        assert not proposal['body'][1]['population_is_original_study_group']
        assert proposal['head']['modality']=='hypothesis_if_the_planned_experiment_is_performed'
        assert proposal['head']['assessed_coordinate']=='17'
        assert proposal['head']['time_quantifier']=='specified_relative_time_from_first_administration'
        assert proposal['head']['assessment_time']=={'anchor':'first_administration_of_this_proposed_episode',
            'value':'17','unit':'source_day_coordinate'} and proposal['head']['effect_size']is None
        assert proposal['head']['statistical_significance']is None and not proposal['head']['continuous_effect_asserted']
        assert proposal['scenario']['comparator_source_case']==proposal['scenario']['intervention_source_case']
        assert len(proposal['support_witness_ids'])==2 and len(proposal['support_primary_families'])==2
        assert proposal['body'][3]['action_status']=='planned'
        assert not proposal['valid_universal_rule']and not proposal['deductively_entailed']
        assert len(proposal['support_primary_families'])==2 and proposal['unverified_changes_ru']
        assert not proposal['novelty']['absence_from_all_source_texts_established']
    assert r['qualified_new_scientific_forecasts']==0 and not r['scientific_success']and not r['graph_advantage_demonstrated']


@pytest.mark.parametrize('change',['raw_day','time_origin','unit','significance','unknown_features','forged_features','intervention',
    'functional_agent','dose','dose_unit','source_family_repeat'])
def test_forged_or_incompatible_source_evidence_is_rejected(corpus,change):
    review,clock,functional,frozen,maps=corpus;r=deepcopy(review);f=deepcopy(functional);w=r['witnesses'][0]
    if change=='raw_day':w['source_day']='26'
    elif change=='time_origin':w['relative_time']['reference_id']='other'
    elif change=='unit':w['relative_time']['unit']='week'
    elif change=='significance':w['pointwise_significance_inferred']=True
    elif change=='unknown_features':w['source_features']['target']=None
    elif change=='forged_features':w['source_features']['target']='mouse_tnfr1'
    elif change=='intervention':w['full_context']['complete_case']['method']['frame']['statements'][0]['roles'][2]['value']='other treatment'
    elif change=='functional_agent':f['functional_certificates'][0]['intervention']='other treatment'
    elif change=='dose':w['dose_groups'][0]['value']='1000'
    elif change=='dose_unit':w['dose_groups'][0]['unit']='mg/kg'
    else:
        # Число семей нельзя изменить отдельно от сохранённого исходного контекста.
        w['primary_family']='invented source family'
    with pytest.raises(ArticleMapError):forecast(r,clock,f,frozen,maps)


def test_one_source_family_never_creates_independent_support(corpus):
    review,clock,functional,frozen,maps=corpus
    witnesses=deepcopy(review['witnesses'])
    for w in witnesses:w['primary_family']='same dataset'
    proofs={p['procedure']:p for p in clock['clock_proofs']};certificates={c['id']:c for c in functional['functional_certificates']}
    assert combine(witnesses,proofs,certificates,'same_facts_without_dependencies')==[]


def test_different_or_unknown_applicability_axes_do_not_generate_crossovers(corpus):
    review,clock,functional,frozen,maps=corpus
    proofs={p['procedure']:p for p in clock['clock_proofs']};certificates={c['id']:c for c in functional['functional_certificates']}
    for value in ('mouse_tnfr1',None):
        witnesses=deepcopy(review['witnesses']);witnesses[0]['source_features']['target']=value
        assert combine(witnesses,proofs,certificates,'same_facts_without_dependencies')==[]


def test_freeze_reuse_and_invalid_new_input_leave_the_previous_candidates(corpus):
    from application.timed_protocol_hypotheses import SealTimedProtocolHypotheses
    class Inputs:
        def __init__(self,data):self.data=data
        def load(self):return self.data
    class MemoryStore:
        def __init__(self):self.seals={}
        def read_seal(self,run_id):return self.seals.get(run_id)
        def seal(self,run_id,artifact):
            if run_id in self.seals:require(fingerprint(self.seals[run_id])==fingerprint(artifact),'Immutable prediction differs')
            else:self.seals[run_id]=artifact
    inputs=Inputs(corpus);store=MemoryStore();service=SealTimedProtocolHypotheses(inputs,store)
    first=service.execute({})
    before=fingerprint(first)
    assert service.execute({})==first
    bad=list(corpus);bad[0]=deepcopy(bad[0]);bad[0]['witnesses'][0]['source_day']='26';inputs.data=tuple(bad)
    with pytest.raises(ArticleMapError):service.execute({})
    assert fingerprint(store.read_seal(first['run_id']))==before
    assert len(store.seals)==1

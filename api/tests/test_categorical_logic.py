"""Существование, контрмодели и научный контекст не подменяются формой стрелок."""
from copy import deepcopy

import pytest

from domain.article_maps import ArticleMapError
from domain.categorical_logic import census, check, holds
from domain.whole_map_categorical import infer, project_record


SCOPE={'study_group':'source','time':'stated protocol','conditions':['explicit class definitions'],'modality':None}


def clause(form,subject,object_,scope=None):
    return {'form':form,'subject':subject,'object':object_,'scope':scope or deepcopy(SCOPE)}


def test_barbara_does_not_create_instances():
    p=[clause('A','S','M'),clause('A','M','P')]
    assert check(p,clause('A','S','P'))['entailed']
    failed=check(p,clause('I','S','P'))
    assert not failed['entailed'] and failed['countermodels'] and failed['counterexample'] is not None
    conditional=check(p,clause('I','S','P'),['S'])
    assert conditional['entailed'] and conditional['existence_conditions']==['S']
    assert not conditional['existential_import'] and not conditional['new_empirical_measurement']


def test_negative_and_particular_premises_have_distinct_logical_effects():
    p=[clause('E','M','P'),clause('I','S','M')]
    assert check(p,clause('O','S','P'))['entailed']
    assert not check(p,clause('E','S','P'))['entailed']
    assert not check([clause('I','S','M'),clause('I','M','P')],clause('I','S','P'))['entailed']


def test_inconsistent_premises_do_not_license_any_conclusion():
    result=check([clause('A','S','P'),clause('O','S','P')],clause('E','S','P'))
    assert not result['premises_consistent'] and not result['entailed']


@pytest.mark.parametrize('change',['scope','unknown','missing_scope','unknown_form','four_terms','unknown_existence'])
def test_unlicensed_logical_inputs_fail(change):
    premises=[clause('A','S','M'),clause('A','M','P')];head=clause('A','S','P');exists=[]
    if change=='scope':premises[0]['scope']['time']='another protocol'
    elif change=='unknown':head['scope']['unknown_context']=True
    elif change=='missing_scope':head['scope']={}
    elif change=='unknown_form':head['form']='probably'
    elif change=='four_terms':head['object']='Q'
    elif change=='unknown_existence':exists=['Q']
    with pytest.raises(ArticleMapError):check(premises,head,exists)


def test_complete_syllogism_census_keeps_existential_conditions_explicit():
    result=census()
    assert result['moods_tested']==256 and result['unconditional']==15 and result['conditional_only']==9
    # Четыре фигуры: крупная и малая посылки имеют разное положение среднего термина.
    rows={(r['figure'],r['mood']):r for r in result['rows']}
    assert rows[1,'AAA']['unconditional'] and rows[1,'AAI']['minimal_existence_conditions']==[['S']]
    assert rows[3,'AAI']['minimal_existence_conditions']==[['M']]
    assert rows[4,'AAI']['minimal_existence_conditions']==[['P']]
    assert not rows[1,'III']['unconditional'] and not rows[1,'III']['minimal_existence_conditions']


def test_all_rejected_moods_have_actual_countermodels():
    scope={'interpretation':'abstract classes'}
    axes={1:(('M','P'),('S','M')),2:(('P','M'),('S','M')),3:(('M','P'),('M','S')),4:(('P','M'),('M','S'))}
    for r in census()['rows']:
        if r['unconditional']:continue
        regions=r['counterexample']['nonempty_regions'];classes={term:set() for term in ('S','M','P')}
        for i,region in enumerate(regions):
            for term in region['inside']:classes[term].add(i)
        to_mask=lambda values:sum(1<<i for i in values)
        for form,(a,b) in zip(r['mood'][:2],axes[r['figure']]):
            assert holds(form,to_mask(classes[a]),to_mask(classes[b]))
        assert not holds(r['mood'][2],to_mask(classes['S']),to_mask(classes['P']))


def record(kid,form,subject,object_):
    predicate,quantifier={'A':('class inclusion','all'),'E':('class disjointness','no'),
        'I':('class overlap','some'),'O':('class noninclusion','some')}[form]
    return {'key':('article',kid),'run_id':'fixed','eligible':True,'provenance':[{'unit_ids':['U1']}],
        'frame':{'kind':'state','action_status':None,'logic':'single','statements':[{
            'predicate':predicate,'roles':[{'role':'subject','value':subject},{'role':'class','value':object_}],
            'scope':{**deepcopy(SCOPE),'quantifier':quantifier},'negated':False,'attributes':[]}]}}


def test_joint_multi_premise_derivation_is_replayable_and_does_not_claim_graph_advantage():
    records={('article','K1'):record('K1','A','S','M'),('article','K2'):record('K2','A','M','P')}
    workflow=record('K3','A','S','P');workflow['frame']['statements'][0]['predicate']='method workflow'
    records[('article','K3')]=workflow
    before=deepcopy(records);groups=[((('article','K1'),('article','K2')),('article','K3'))]
    result=infer(records,groups)
    assert result['admitted_blocks']==2 and records==before
    assert result['consequences']['graph']==result['consequences']['without_dependencies']
    candidates=result['consequences']['graph'];assert len(candidates)==1
    c=candidates[0];assert c['conclusion']['form']=='A' and c['conclusion']['subject']=='S' and c['conclusion']['object']=='P'
    assert len(c['premises'])==2 and c['proof']['entailed'] and c['proof_graph']['visible_dag']
    assert not c['novel_empirical_prediction'] and not result['graph_advantage_demonstrated']
    assert not infer(records,[])['consequences']['graph']


def test_single_dependency_connects_explicit_definition_premises_for_syllogism():
    # Явные определения связываются только прямой зависимостью и сохраняют область источника.
    records={('article','K1'):record('K1','E','M','D'),('article','K2'):record('K2','A','S','M')}
    group=((('article','K1'),),('article','K2'))
    result=infer(records,[group])
    graph=result['consequences']['graph'];without=result['consequences']['without_dependencies']
    assert len(graph)==len(without)==1
    candidate=graph[0]
    assert candidate['conclusion']['form']=='E'
    assert {candidate['conclusion']['subject'],candidate['conclusion']['object']}=={'S','D'}
    assert {(p['article_id'],p['knowledge_id']) for p in candidate['premises']}=={('article','K1'),('article','K2')}
    assert candidate['proof']['entailed'] and not candidate['novel_empirical_prediction']
    assert not result['graph_advantage_demonstrated']


@pytest.mark.parametrize('case',['unknown_body','unknown_head','self','duplicate'])
def test_bad_dependency_references_fail_closed(case):
    records={('article','K1'):record('K1','A','S','M'),('article','K2'):record('K2','A','M','P')}
    body=[('article','K1')];head=('article','K2')
    if case=='unknown_body':body=[('target','unknown')]
    elif case=='unknown_head':head=('target','unknown')
    elif case=='self':head=body[0]
    else:body*=2
    with pytest.raises(ArticleMapError):infer(records,[(tuple(body),head)])


@pytest.mark.parametrize('change',['association','no_quantifier','negation','modality','argument','unknown_context','extra_constraint','role','scope'])
def test_graph_shape_cannot_license_untyped_scientific_inference(change):
    r=record('K1','A','S','M');s=r['frame']['statements'][0]
    if change=='association':s['predicate']='associated with'
    elif change=='no_quantifier':s['scope']['quantifier']=None
    elif change=='negation':s['negated']=True
    elif change=='modality':s['scope']['modality']='may'
    elif change=='argument':r['frame']['logic']='argument'
    elif change=='unknown_context':r['eligible']=False
    elif change=='extra_constraint':s['attributes']=[{'name':'mean','value':1,'unit':None}]
    elif change=='role':s['roles'][0]['role']='cause'
    elif change=='scope':s['scope'].update(time=None,conditions=[],study_group=None)
    assert project_record(r)[0] is None


def test_compound_block_is_not_selectively_reduced_to_a_convenient_statement():
    r=record('K1','A','S','M');r['frame']['logic']='conjunction'
    other=deepcopy(r['frame']['statements'][0]);other['predicate']='observed hazard ratio'
    r['frame']['statements'].append(other)
    assert project_record(r)[0] is None


def test_symmetric_equivalence_and_hidden_class_cycles_do_not_create_visible_cycles():
    records={('article','K1'):record('K1','A','S','M'),('article','K2'):record('K2','A','M','S')}
    result=infer(records,[])
    assert not result['consequences']['without_dependencies']
    assert not check([clause('A','S','M'),clause('A','M','S')],clause('I','S','M'))['entailed']

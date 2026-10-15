"""Синтетические контроли происхождения и запрета прогнозной интерпретации."""
from copy import deepcopy
from dataclasses import replace
import pytest
from application.observed_evidence_diagnostic import CompareObservedStudyEvidence
from domain.article_maps import ArticleMapError, digest, fingerprint
from domain.research_semantics import Evidence, SemanticClaim, context_value
from domain.statistical_evidence_derivation import StatisticalEvidence


class MemoryArtifacts:
    def __init__(self):
        self.saved={}

    def audit(self,id,artifact):
        if id in self.saved:
            assert fingerprint(self.saved[id])==fingerprint(artifact)
        self.saved[id]=deepcopy(artifact)


def studies():
    result=[]
    for id,effect,unit,estimate,ci,p,orientation in [('A','odds_ratio','dimensionless',2.9,(1.1,7.5),0.031,True),
                                                  ('B','linear_coefficient','score/year',-0.13,(-0.47,0.21),0.447,False)]:
        text='Synthetic provenance control '+id; h=digest(text)
        evidence=Evidence(id,'test-run-'+id,h,'2020-01-01',id,'own_result',({'start':0,'end':len(text),'text':text,'offset_encoding':'unicode_code_points'},))
        name='odds ratio' if effect=='odds_ratio' else 'beta'
        claim=SemanticClaim(id,id,'associated with',{'exposure':'synthetic biomarker','outcome':'synthetic decline'},False,None,None,
                            {'study':context_value(id),'population':context_value(None,'not_reported')},
                            ({'name':name,'value':estimate,'unit':unit},{'name':name+' ci','value':list(ci),'unit':unit},{'name':'p','value':p,'unit':'dimensionless'}),
                            None,'single','Synthetic test claim',evidence)
        result.append({'claim':claim,'source':{'text':text,'sha256':h,'content_end':len(text)},
                       'statistical_evidence':StatisticalEvidence(effect,unit,estimate,ci,p,orientation)})
    return result


def test_reconstruction_preserves_unknown_context_and_is_never_a_forecast():
    store=MemoryArtifacts(); scenario=CompareObservedStudyEvidence(store)
    first=scenario.execute(studies(),'2022-12-31'); second=scenario.execute(studies(),'2022-12-31')
    assert first==second and len(store.saved)==1
    assert first['comparison']['relation']=='context_mismatch'
    assert first['comparison']['unknown']==['population']
    assert [x['derivation']['label'] for x in first['derived_labels']]==['positive_association','not_statistically_detected']
    assert not first['forecast_issued'] and not first['future_target_selected'] and first['new_training_sources']==0


@pytest.mark.parametrize('mutation',['future','quote','boundary','statistical_value','abstract'])
def test_invalid_explicit_input_is_rejected_before_persistence(mutation):
    inputs=studies(); claim=inputs[0]['claim']; store=MemoryArtifacts()
    if mutation=='future':
        inputs[0]['claim']=replace(claim,evidence=replace(claim.evidence,available_on='2023-01-01'))
    elif mutation=='quote':
        inputs[0]['source']['text']='Altered source'
    elif mutation=='boundary':
        inputs[0]['source']['content_end']=1
    elif mutation=='abstract':
        inputs[0]['claim']=replace(claim,evidence=replace(claim.evidence,presentation='review'))
    else:
        inputs[0]['statistical_evidence']=replace(inputs[0]['statistical_evidence'],estimate=3.5)
    with pytest.raises(ArticleMapError):
        CompareObservedStudyEvidence(store).execute(inputs,'2022-12-31')
    assert not store.saved


def test_missing_ci_is_an_explicit_insufficient_data_result():
    inputs=studies(); c=inputs[0]['claim']
    inputs[0]['claim']=replace(c,measurements=tuple(m for m in c.measurements if m['name']!='odds ratio ci'))
    inputs[0]['statistical_evidence']=replace(inputs[0]['statistical_evidence'],ci95=None)
    result=CompareObservedStudyEvidence(MemoryArtifacts()).execute(inputs,'2022-12-31')
    assert result['derived_labels'][0]['derivation']['label']=='insufficient_data'

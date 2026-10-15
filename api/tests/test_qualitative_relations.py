"""Качественный результат сохраняет научные ограничения и два слоя интерпретации."""
from copy import deepcopy
from pathlib import Path
import json
import pytest
from domain.article_maps import ArticleMapError,digest
from domain.qualitative_relations import validate_claim,compare_claims,forecast_fold,evaluate_fold
from application.qualitative_relations import SealQualitativeRelations,EvaluateQualitativeRelations
from infrastructure.qualitative_relations import FileQualitativeInputs,FileQualitativeControls
from infrastructure.development_prediction_store import FilePredictionStore

ROOT=Path(__file__).resolve().parents[2]/'eval/free_prediction/qualitative-relations-pilot-v1'

def records():return json.loads((ROOT/'annotation-spec.json').read_text(encoding='utf-8'))['claims']
def claim(identifier):return deepcopy(next(c for c in records() if c['id']==identifier))

def test_nonmemory_education_pattern_is_same_but_facts_are_not_equivalent():
    r=compare_claims(claim('M-edu-na'),claim('K-edu-na'))
    assert r['relation']=='same_pattern' and r['independent_cohorts']==2
    assert r['scientific_fact_equivalence'] is False and r['logical_contradiction'] is False
    assert r['context_differences']['analysis'] and r['unknown_context']['critical']

def test_nondetection_is_not_a_zero_or_inverse_biological_effect():
    c=claim('R-edu-a-adjusted');validate_claim(c)
    assert c['result']['direction']=='higher' and c['result']['statistical_finding']=='not_detected'
    assert not any(s['negated'] for s in c['semantic_frame']['statements'])

@pytest.mark.parametrize('identifier,expected',[
    ('R-edu-a-raw','different_estimand'),('R-edu-na','different_phenotype'),('K-edu-a','direction_disagreement')])
def test_raw_adjusted_phenotype_and_direction_changes_are_distinguished(identifier,expected):
    assert compare_claims(claim('R-edu-a-adjusted'),claim(identifier))['relation']==expected

def test_significance_change_under_mortality_imputation_is_not_logical_contradiction():
    r=compare_claims(claim('C-ocind-sex-observed'),claim('C-ocind-sex-corrected'))
    assert r['relation']=='statistical_disagreement' and r['direction_agreement'] is True
    assert r['logical_contradiction'] is False

def test_unknown_direction_is_not_equal_direction():
    r=compare_claims(claim('M-sex'),claim('U-sex'))
    assert r['relation']=='partial_pattern' and r['direction_agreement'] is None

def test_all_nine_real_controls():
    pairs=json.loads((ROOT/'control-pairs.json').read_text(encoding='utf-8'))['pairs']
    for p in pairs:assert compare_claims(claim(p['left']),claim(p['right']))['relation']==p['expected']

def fold(training=None):
    return {'fold_id':'synthetic','withheld_family':'EAS','training':training or [claim('M-edu-na'),claim('R-edu-na')]}

def test_two_independent_cohorts_support_direction_but_not_significance_or_causality():
    f=forecast_fold(fold());p=f['predictions']['semantic'][0]
    assert p['expected_direction']=='higher' and p['cohorts']==['Mayo','WHICAP']
    assert p['expected_significance'] is None and not p['causal'] and not p['novel_claim']
    assert evaluate_fold(f,[claim('K-edu-na')])['modes']['semantic']['counts']=={'qualitative_pattern_match':1}

def test_same_cohort_duplicates_cannot_replace_independent_support():
    a=claim('M-edu-na');b=deepcopy(a);b['id']='other';b['source_id']='other-publication'
    assert forecast_fold(fold([a,b]))['predictions']['semantic']==[]

def test_opposing_detected_association_blocks_transfer():
    a=claim('M-edu-na');b=claim('R-edu-na');b['result']['direction']='lower'
    b['semantic_frame']['statements'][0]['value']='lower'
    assert forecast_fold(fold([a,b]))['predictions']['semantic']==[]

def test_nondetection_neither_confirms_nor_refutes_a_transfer_hypothesis():
    f=forecast_fold(fold());c=claim('K-edu-na');c['result']['statistical_finding']='not_detected'
    c['semantic_frame']['statements'][1]['value']='not_detected'
    assert evaluate_fold(f,[c])['modes']['semantic']['counts']=={'uncertain':1}

def test_detected_opposite_is_a_transfer_failure_not_different_cohort_logical_contradiction():
    f=forecast_fold(fold());c=claim('K-edu-na');c['result']['direction']='lower';c['semantic_frame']['statements'][0]['value']='lower'
    r=evaluate_fold(f,[c])['modes']['semantic']
    assert r['counts']=={'inconsistent_transfer':1}
    assert all(not a['comparison']['logical_contradiction'] for a in r['rows'][0]['context_audits'])

def test_context_is_retained_and_not_mutated():
    f=fold();before=deepcopy(f);forecast_fold(f);assert f==before

def test_no_withheld_family_leakage_even_through_repeat_publication():
    c=claim('K-edu-na');c['source_id']='another-eas'
    with pytest.raises(ArticleMapError,match='leaked'):forecast_fold(fold([c]))

@pytest.mark.parametrize('change',[
    lambda c:c['result'].update(effect_size='0.95'),lambda c:c['result'].update(direction='biological_absence'),
    lambda c:c['result'].update(causal_status='causal'),lambda c:c['semantic_frame']['statements'][0].update(value='lower'),
    lambda c:c.update(expected_answer='higher'),lambda c:c.update(provenance=[]),
])
def test_invalid_result_or_frame_rejected(change):
    c=claim('M-edu-na');change(c)
    with pytest.raises(ArticleMapError):validate_claim(c)

def test_fragments_are_exact_unicode_and_sources_unchanged():
    data=json.loads((ROOT/'annotation-spec.json').read_text(encoding='utf-8'))
    for p in data['evidence'].values():
        text=Path(data['sources'][p['source_id']]['path']).read_text(encoding='utf-8')
        assert digest(text)==p['source_sha256'] and text[p['start']:p['end']]==p['text'] and digest(p['text'])==p['text_sha256']

def test_seal_reads_only_manifest_and_six_training_folds(monkeypatch,tmp_path):
    import socket
    monkeypatch.setattr(socket,'create_connection',lambda *a,**k:pytest.fail('Network forbidden'))
    port=FileQualitativeInputs(ROOT/'prepared/manifest.json');store=FilePredictionStore(tmp_path)
    result=SealQualitativeRelations(port,store).execute({'code':'fixed'})
    assert len(port.reads)==7 and not any('hidden-controls' in p or 'article.layout' in p for p in port.reads)
    assert len(result['folds'])==6 and result['new_scientific_predictions']==0

def test_evaluator_cannot_read_controls_before_seal_or_after_code_change(tmp_path):
    port=FileQualitativeControls(ROOT/'prepared/hidden-controls.json');store=FilePredictionStore(tmp_path)
    with pytest.raises(ArticleMapError):EvaluateQualitativeRelations(port,store).execute('f'*64,{'code':'old'})
    assert port.reads==[]
    seal=SealQualitativeRelations(FileQualitativeInputs(ROOT/'prepared/manifest.json'),store).execute({'code':'fixed'})
    with pytest.raises(ArticleMapError):EvaluateQualitativeRelations(port,store).execute(seal['run_id'],{'code':'changed'})
    assert port.reads==[]

def test_idempotent_seal_and_primary_qualitative_matches_are_retrospective(tmp_path):
    store=FilePredictionStore(tmp_path);inputs=FileQualitativeInputs(ROOT/'prepared/manifest.json')
    app=SealQualitativeRelations(inputs,store);a=app.execute({'code':'fixed'});b=app.execute({'code':'fixed'})
    assert a==b
    e=EvaluateQualitativeRelations(FileQualitativeControls(ROOT/'prepared/hidden-controls.json'),store).execute(a['run_id'],{'code':'fixed'})
    assert e['totals']['semantic']['qualitative_pattern_match']==3 and e['new_scientific_predictions']==0
    assert not e['independent_success']

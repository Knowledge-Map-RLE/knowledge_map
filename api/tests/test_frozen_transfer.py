"""Фиксация свободных гипотез без выбора вопроса и знания цели."""
from copy import deepcopy
from pathlib import Path
import pytest
from domain.article_maps import ArticleMapError
from domain.frozen_transfer import generate_transfer
from infrastructure.frozen_transfer import FileTransferInputs
from application.frozen_transfer import FreezeTransfer
from infrastructure.development_prediction_store import FilePredictionStore

ROOT=Path(__file__).resolve().parents[2]/'eval/free_prediction/frozen-transfer-checkpoint-v1'
def inputs():return FileTransferInputs(ROOT/'manifest.json').read_inputs()

def test_free_generation_preserves_two_patterns_and_strong_baselines():
    r=generate_transfer(inputs());m=r['forecast']['predictions']
    assert [len(m[k]) for k in ['semantic','known_union','frequency']]==[2,17,11]
    assert len(r['training_claims'])==23 and len(r['training_families'])==6
    assert len(r['normalization_proofs'])==5
    assert not r['target_chosen'] and not r['scientific_success'] and not r['graph_advantage_demonstrated']
    for c in m['semantic']:
        assert c['expected_significance'] is None and c['expected_effect_size'] is None and not c['causal']
        assert not c['support_semantics']['logical_entailment']
        assert not c['support_semantics']['all_premises_jointly_required']
        assert any(b['signature']==c['signature'] and b['expected_direction']==c['expected_direction'] for b in m['known_union'])

def test_two_claims_from_one_cohort_are_not_replications():
    d=inputs();d['annotation']['records']=[n for n in d['annotation']['records'] if n['claim']['family_id']=='LEILA75+']
    assert not generate_transfer(d)['forecast']['predictions']['semantic']

@pytest.mark.parametrize('field,value',[('model_calls',1),('target_access',True),('question','Does age affect MCI?')])
def test_policy_change_rejected(field,value):
    d=inputs();d['protocol'][field]=value
    with pytest.raises(ArticleMapError):generate_transfer(d)

def test_source_nondetection_does_not_become_zero_effect():
    r=generate_transfer(inputs())
    non=[c for c in r['training_claims'] if c['result']['statistical_finding']=='not_detected']
    assert non and all(c['result']['causal_status']=='observational' for c in non)

def test_opposing_detected_direction_blocks_that_pattern():
    d=inputs();n=next(n for n in d['annotation']['records'] if n['claim']['id']=='M-edu-na')
    n['claim']['result']['direction']='lower';n['claim']['semantic_frame']['statements'][0]['value']='lower'
    r=generate_transfer(d)
    assert all(c['signature']['factor']!='education' for c in r['forecast']['predictions']['semantic'])

def test_read_receipt_excludes_controls_and_metadata():
    port=FileTransferInputs(ROOT/'manifest.json');port.read_inputs()
    assert all('hidden-' not in p and 'metadata-' not in p and 'question_prediction' not in p for p in port.reads)

def test_frozen_artifact_is_repeatable_and_preserves_source_context(tmp_path):
    port=FileTransferInputs(ROOT/'manifest.json');store=FilePredictionStore(tmp_path);u=FreezeTransfer(port,store)
    first=u.execute({'code':'frozen'});assert u.execute({'code':'frozen'})==first
    assert len(first['generation']['forecast']['predictions']['semantic'][0]['premises'])==3
    assert all(p['context']['critical'] for p in first['generation']['forecast']['predictions']['semantic'][0]['premises'])
    assert first['generation']['status']=='frozen_before_target_selection'

def test_different_implementation_has_separate_artifact(tmp_path):
    u=FreezeTransfer(FileTransferInputs(ROOT/'manifest.json'),FilePredictionStore(tmp_path))
    a=u.execute({'version':'a'});b=u.execute({'version':'b'})
    assert a['run_id']!=b['run_id']

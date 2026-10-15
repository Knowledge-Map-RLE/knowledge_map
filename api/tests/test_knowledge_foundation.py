"""Фундаментальные следствия, научные ограничения и изоляция контроля."""
from copy import deepcopy
import json
from pathlib import Path
import pytest
from domain.article_maps import ArticleMapError, digest, fingerprint
from domain.knowledge_foundation import (validate_foundation, validate_dag, invert_ratio, convert_measure,
    compose_universal, normalize, forecast_native_fold, validate_proof_graph)
from application.knowledge_foundation import SealFoundationPilot, EvaluateFoundationPilot
from infrastructure.knowledge_foundation import FileFoundationInputs, FileFoundationControls
from infrastructure.development_prediction_store import FilePredictionStore

ROOT = Path(__file__).resolve().parents[2]/'eval/free_prediction/foundation-pilot-v1'

def read(name): return json.loads((ROOT/name).read_text(encoding='utf-8'))
def foundation(): return read('prepared/foundation.json')
def record(identifier): return deepcopy(next(n for n in read('annotation-spec.json')['records'] if n['claim']['id']==identifier))

def test_explicit_foundation_has_bilingual_blocks_and_justified_dag():
    f=foundation(); ranks=validate_foundation(f)
    assert len(f['knowledge'])==12 and ranks['negative_model_increment']==2
    assert all(b['text'] and b['text_ru'] and b['provenance'] for b in f['knowledge'])

@pytest.mark.parametrize('estimate,bounds',[('0',None),('-1',None),('NaN',None),('0.95',['0','1']),('0.95',['1','2'])])
def test_invalid_ratio_or_interval_rejected(estimate,bounds):
    with pytest.raises(ArticleMapError): invert_ratio(estimate,bounds)

def test_inverse_and_interval_orientation_are_correct():
    value,bounds=invert_ratio('0.95',['0.90','0.997'])
    assert value.startswith('1.0526315') and bounds[0].startswith('1.003009') and bounds[1].startswith('1.111111')

def test_nondetection_is_preserved_after_reverse_not_a_protective_fact():
    c,p=normalize(record('U-sex'),foundation(),'dependencies')
    assert c['result']['direction']=='lower' and c['result']['statistical_finding']=='not_detected'
    assert p['causal'] is False and p['new_empirical_knowledge'] is False
    assert c['context']==record('U-sex')['claim']['context']

def test_mode_comparison_does_not_silently_reverse_a_direction():
    a=record('K-edu-na');before=deepcopy(a)
    c,p=normalize(a,foundation(),'comparison')
    assert c['contrast']=='more_vs_less' and c['result']['direction']=='lower' and p is None
    derived,proof=normalize(a,foundation(),'derivation')
    assert derived['contrast']=='less_vs_more' and derived['result']['direction']=='higher'
    assert proof['status']=='conditional_mathematical_consequence' and a==before

@pytest.mark.parametrize('change',[
    lambda n:n['basis'].update(same_model_context=None),
    lambda n:n['basis'].update(ratio=None),
    lambda n:n['basis']['linear_increment'].update(model='unspecified'),
    lambda n:n['basis'].update(evidence_ids=[]),
])
def test_unknown_or_changed_reversal_assumptions_block_operation(change):
    n=record('K-edu-na');change(n)
    with pytest.raises(ArticleMapError):normalize(n,foundation(),'dependencies')

def test_required_rule_is_not_an_implicit_fallback():
    f=foundation();f['knowledge']=[b for b in f['knowledge'] if b['knowledge_id']!='reciprocal_ratio']
    with pytest.raises(ArticleMapError):normalize(record('K-edu-na'),f,'derivation')

def test_source_pair_is_computed_only_by_the_derivation_operator():
    n=record('L-sex');assert isinstance(n['basis']['ratio'],dict)
    c,p=normalize(n,foundation(),'derivation')
    assert p['derived_ratio'].startswith('0.689655') and c['result']['statistical_finding']=='not_reported'

def test_dimension_guard_keeps_probability_distinct_from_person_time_rate():
    f=foundation()
    assert convert_measure('9.9','incidence_rate','1000','incidence_rate','1',f)=='0.0099'
    with pytest.raises(ArticleMapError):convert_measure('9.9','incidence_rate','1000','incidence_proportion','100',f)
    with pytest.raises(ArticleMapError):convert_measure('110','incidence_proportion','100','incidence_proportion','1',f)

def premise(a,b):return {'subject':a,'object':b,'predicate':'subset','quantifier':'all','context':'same diagnostic definition'}

def test_universal_chain_preserves_quantifier_and_does_not_invent_existence():
    c=compose_universal(premise('A','B'),premise('B','C'),foundation())
    assert c['object']=='C' and c['quantifier']=='all' and c['existence_asserted'] is False

@pytest.mark.parametrize('change',[
    lambda p:p.update(quantifier='some'),lambda p:p.update(predicate='associated_with'),
    lambda p:p.update(context=None),lambda p:p.update(context='other definition'),
])
def test_existential_correlation_or_unknown_context_cannot_use_universal_chain(change):
    p=premise('B','C');change(p)
    with pytest.raises(ArticleMapError):compose_universal(premise('A','B'),p,foundation())

@pytest.mark.parametrize('change',[
    lambda g:g['edges'].pop(), lambda g:g['joint_premises'].pop(),
    lambda g:g['condition'].update(same_model_context=False),
])
def test_joint_premise_graph_detects_missing_dependencies(change):
    n=record('K-edu-na');f=foundation();_,p=normalize(n,f,'dependencies');g=deepcopy(p['graph']);change(g)
    with pytest.raises(ArticleMapError):validate_proof_graph(n,f,p,g)

def test_proof_hashes_cannot_be_rebound_to_another_source():
    n=record('K-edu-na');f=foundation();_,p=normalize(n,f,'dependencies');n['claim']['source_id']='other'
    with pytest.raises(ArticleMapError):validate_proof_graph(n,f,p,p['graph'])

def test_visible_cycles_and_unknown_references_are_rejected():
    nodes=[{'id':'a'},{'id':'b'}]
    for edges in [[{'source':'a','target':'b'},{'source':'b','target':'a'}],[{'source':'a','target':'unknown'}]]:
        with pytest.raises(ArticleMapError):validate_dag(nodes,edges)

def test_hidden_semantic_cycle_does_not_create_visible_edges():
    f=foundation();f['knowledge'][0]['frame']['participants']=['negative_model_increment']
    assert validate_foundation(f)['negative_model_increment']==2

def test_training_cannot_include_withheld_cohort():
    n=record('K-edu-na')
    with pytest.raises(ArticleMapError,match='leaked'):
        forecast_native_fold({'fold_id':'x','withheld_family':'EAS','training':[n]},foundation())

def test_new_provenance_includes_actual_mayo_estimate_and_leila_sex_row():
    s=read('annotation-spec.json')
    assert '2.09' in s['evidence']['R-edu-na']['text'] and '1.30' in s['evidence']['U-sex']['text']
    assert len(s['repairs'])==5
    for e in s['evidence'].values():
        text=Path(s['sources'][e['source_id']]['path']).read_text(encoding='utf-8')
        assert digest(text)==e['source_sha256'] and text[e['start']:e['end']]==e['text']

def test_reader_hashes_and_paths_block_undeclared_changes(tmp_path):
    manifest=read('prepared/manifest.json');manifest['foundation']['path']='../annotation-spec.json'
    path=tmp_path/'manifest.json';path.write_text(json.dumps(manifest),encoding='utf-8')
    with pytest.raises(ArticleMapError,match='path differs'):FileFoundationInputs(path).read_inputs()

def test_control_file_cannot_be_declared_as_a_training_input(tmp_path):
    manifest=read('prepared/manifest.json');manifest['folds'][0]['path']='hidden-controls.json'
    path=tmp_path/'manifest.json';path.write_text(json.dumps(manifest),encoding='utf-8')
    port=FileFoundationInputs(path)
    with pytest.raises(ArticleMapError,match='Undeclared'):port.read_inputs()
    assert port.reads==[str(path.resolve())]

def test_network_disabled_seal_reads_only_eight_declared_inputs(monkeypatch,tmp_path):
    import socket
    monkeypatch.setattr(socket,'create_connection',lambda *a,**k:pytest.fail('Network forbidden'))
    port=FileFoundationInputs(ROOT/'prepared/manifest.json');store=FilePredictionStore(tmp_path)
    app=SealFoundationPilot(port,store);a=app.execute({'code':'fixed'});b=app.execute({'code':'fixed'})
    assert a==b and len(port.reads)==16
    assert not any('hidden-controls' in p or 'article.layout' in p for p in port.reads)
    assert len(a['folds'])==6 and a['new_scientific_predictions']==0

def test_controls_unread_before_seal_or_if_code_changed(tmp_path):
    port=FileFoundationControls(ROOT/'prepared/hidden-controls.json');store=FilePredictionStore(tmp_path)
    with pytest.raises(ArticleMapError):EvaluateFoundationPilot(port,store).execute('f'*64,{'code':'fixed'})
    assert port.reads==[]
    seal=SealFoundationPilot(FileFoundationInputs(ROOT/'prepared/manifest.json'),store).execute({'code':'fixed'})
    with pytest.raises(ArticleMapError):EvaluateFoundationPilot(port,store).execute(seal['run_id'],{'code':'changed'})
    assert port.reads==[]

def test_four_modes_keep_three_known_matches_separate_from_new_science(tmp_path):
    store=FilePredictionStore(tmp_path);seal=SealFoundationPilot(FileFoundationInputs(ROOT/'prepared/manifest.json'),store).execute({'code':'fixed'})
    e=EvaluateFoundationPilot(FileFoundationControls(ROOT/'prepared/hidden-controls.json'),store).execute(seal['run_id'],{'code':'fixed'})
    assert e['totals']['articles'].get('qualitative_pattern_match',0)==0
    assert e['totals']['comparison'].get('qualitative_pattern_match',0)==0
    assert e['totals']['derivation']['qualitative_pattern_match']==3
    assert e['totals']['dependencies']==e['totals']['derivation']
    assert not e['independent_scientific_success'] and e['new_scientific_predictions']==0
    controls=read('prepared/hidden-controls.json')
    for f in seal['folds']:
        ids={n['claim']['id'] for n in controls['controls'][f['fold_id']]}
        assert all(p['source_claim'] not in ids for p in f['proofs']['dependencies'])

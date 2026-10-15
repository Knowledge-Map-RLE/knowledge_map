"""Происхождение не является условием; ограничения и изоляция сохраняются."""
import json
from copy import deepcopy
from pathlib import Path

import pytest
from domain.article_maps import fingerprint, digest
from domain.knowledge_development import model_contract, validate_development_map
from domain.semantic_operator_learning import ordered_frame
from infrastructure.schema6_operator_projection import project as project_v1
from infrastructure.schema6_operator_projection_v2 import project, ORIGIN_ATTRIBUTES
from infrastructure.expanded_operator_corpus import ExpandedOperatorCorpus

ROOT = Path(__file__).resolve().parents[2]/'eval/question_prediction/il6-plasma-global-v1/expanded-semantic-three-v1'
def read(path): return json.loads(path.read_text(encoding='utf-8'))
def prepared(pmc): return read(ROOT/'maps-v2'/pmc/'prepared.json')
def projected(row): return project(row['map'],row['family'],row['published_on'],row['annotations'])


@pytest.mark.parametrize('pmc,blocks,claims,transitions,depth', [
    ('PMC4336104',23,23,12,6),('PMC5005896',25,26,11,6),('PMC6218168',28,29,11,4)])
def test_real_expanded_maps_validate_and_keep_scientific_scope(pmc,blocks,claims,transitions,depth):
    row=prepared(pmc); value=row['map']; graph=value['graph']; source=value['source']
    assert digest(source['text'])==source['sha256']
    checked=validate_development_map(model_contract(graph),source)
    assert len(graph['knowledge'])==blocks
    assert sum(len(k['semantic_frame']['statements']) for k in graph['knowledge'])==claims
    assert len(graph['transitions'])==transitions and checked['analysis']['depth']==depth
    assert 'References' in source['text'][source['content_end']:]
    for unit in source['units']:
        assert source['text'][unit['start']:unit['end']]==unit['text']
    assert all(k['provenance']['unit_ids'] for k in graph['knowledge'])
    assert set(value['translations']['ru']['knowledge_labels'])=={k['knowledge_id'] for k in graph['knowledge']}


def test_origin_metadata_moves_to_trace_without_mutating_map():
    row=prepared('PMC6218168'); before=fingerprint(row)
    old=project_v1(row['map'],row['family'],row['published_on'],row['annotations'])
    new=projected(row)
    assert new['binding']['projection_version']=='schema6-operator-projection-2'
    assert fingerprint(row)==before
    for a,b in zip(old['knowledge'],new['knowledge']):
        assert a.frame['kind']==b.frame['kind'] and a.frame['action_status']==b.frame['action_status']
        for sa,sb in zip(a.frame['statements'],b.frame['statements']):
            assert {k:v for k,v in sa.items() if k!='attributes'}=={k:v for k,v in sb.items() if k!='attributes'}
            assert sb['attributes']==[v for v in sa['attributes'] if v['name'] not in ORIGIN_ATTRIBUTES]
        assert b.binding['frame_sha256']==fingerprint(b.frame)
        assert b.binding['source_sha256']==a.binding['source_sha256']
        assert b.binding['provenance'][0]['comparison_origin_metadata']


@pytest.mark.parametrize('dimension', ['stratum','specimen','conditions','negation','numbers','action_status'])
def test_scientific_differences_are_not_abstracted_with_source_ids(dimension):
    row=prepared('PMC6218168'); changed=deepcopy(row)
    k=changed['map']['graph']['knowledge'][0]; statement=k['semantic_frame']['statements'][0]
    if dimension in {'stratum','specimen'}:
        statement['qualifiers']['attributes'].append({'name':dimension,'value':'changed clinical condition','unit':None})
    elif dimension=='conditions': statement['conditions'].append('different follow-up definition')
    elif dimension=='negation': statement['negated']=not statement['negated']
    elif dimension=='numbers': statement['qualifiers']['attributes'][0]['value']=60
    else: k['kind']='action'; k['action_status']='unresolved'
    assert ordered_frame(projected(row)['knowledge'][0].frame)!=ordered_frame(projected(changed)['knowledge'][0].frame)


def test_two_strata_and_distinct_estimands_keep_four_separate_il6_results():
    row=prepared('PMC6218168'); data=projected(row)
    stats=next(s for s in read(ROOT/'prepared-v2/summary.json') if s['pmcid']=='PMC6218168')
    ids={stats['key_to_id'][key] for key in ['il6_slope_no','il6_slope_mci','il6_hr_no','il6_hr_mci']}
    claims=[k for k in data['knowledge'] if k.binding['provenance'][0]['knowledge_id'] in ids]
    assert len({fingerprint(k.frame) for k in claims})==4
    assert {a['unit'] for k in claims for s in k.frame['statements'] for a in s['attributes'] if a['name']=='estimate'}=={'3mse points/6-month visit per sd'}
    rejection=data['rejected'][0]
    assert rejection=={'transition_id':'T7','reason':'more_than_three_joint_semantic_premises'}
    target=next(t for t in row['map']['graph']['transitions'] if t['id']=='T7')
    assert len(target['sources'])==5


def test_training_and_application_files_do_not_read_withheld_full_map_or_outcomes():
    corpus=ExpandedOperatorCorpus(read(ROOT/'prepared-v2/catalog.json'))
    train=corpus.training(['PMC4336104','PMC5005896']); available=corpus.premises('PMC6218168')
    assert {k.family for k in train['knowledge']}=={'health-aging-body-composition','tokyo-oldest-old-survey-on-total-health'}
    assert len(available['knowledge'])==3
    assert corpus.reads==[{'stage':'training','references':['PMC4336104','PMC5005896']},{'stage':'premises','reference':'PMC6218168'}]
    # Физически раздельный файл не содержит удержанных знаний и клинических результатов.
    entry=corpus.catalog['PMC6218168']; raw=read(Path(entry['premises_path']))
    assert set(k['knowledge_id'] for k in raw['map']['graph']['knowledge'])==set(entry['premise_knowledge_ids'])
    assert not set(entry['premise_knowledge_ids']) & set(entry['outcome_knowledge_ids'])


def test_table_and_author_interpretation_both_ground_compound_facts():
    rows=[('PMC5005896','cmv_contrast','0.36','0.878'),('PMC6218168','cox','Cox regression','stratified according to clinic')]
    for pmc,key,a,b in rows:
        result=prepared(pmc)['map']; stats=next(s for s in read(ROOT/'prepared-v2/summary.json') if s['pmcid']==pmc)
        k=next(k for k in result['graph']['knowledge'] if k['knowledge_id']==stats['key_to_id'][key])
        support='\n'.join(u['text'] for u in result['source']['units'] if u['id'] in k['provenance']['unit_ids'])
        assert a in support and b in support

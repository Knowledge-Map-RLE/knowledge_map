"""Абстракция измеряемого свойства проверяется без отождествления шкал и научных эффектов."""
from copy import deepcopy
from pathlib import Path
import json
import pytest
from domain.article_maps import ArticleMapError,fingerprint
from domain.measurement_orientation import ordered_direction,project,analyze
from domain.evidence_origin_audit import validate_origins
from infrastructure.measurement_orientation import load_sources


@pytest.mark.parametrize('effect,orientation,expected',[
    ('improved','higher_is_worse','lower'),('improved','higher_is_better','higher'),
    ('worsened','higher_is_worse','higher'),('worsened','higher_is_better','lower'),
    ('not_detected','higher_is_worse',None),('not_detected','higher_is_better',None),
    ('unknown','higher_is_worse',None),('unknown','higher_is_better',None),
    ('improved','unknown',None),('worsened','unknown',None),('unknown','unknown',None),('not_detected','unknown',None)])
def test_ordered_direction_keeps_measurement_orientation_and_unknown(effect,orientation,expected):
    assert ordered_direction(effect,orientation)==expected


@pytest.mark.parametrize('effect,orientation',[('no_effect','higher_is_worse'),('improved','unspecified')])
def test_unregistered_semantics_never_become_a_direction(effect,orientation):
    with pytest.raises(ArticleMapError):ordered_direction(effect,orientation)


@pytest.fixture(scope='module')
def corpus():
    root=Path(__file__).resolve().parents[2]/'eval'/'whole_map_forecast'
    values=load_sources(root/'interval-summary-operators-v1'/'runs'/'f402b03ffb48e868e3216a344d41df4bce89ae109e6afea5c3597520e951f423',
        root/'therapeutic-comparator-v1'/'applicability-runs'/'ce2acc6c160c76d70c9f1884357c3758875b91ee0c7b03e54d5e5a80bf132074')
    audit=json.loads((root/'measurement-orientation-v1'/'prepared-v2'/'audit.json').read_bytes())
    return (*values,audit)


def test_real_scales_preserve_source_numbers_participants_scope_and_whole_parents(corpus):
    previous,frozen,maps,origin_audit,cases,audit=corpus;before=fingerprint(corpus)
    origins=validate_origins(maps,origin_audit);views,proofs=project(frozen,maps,cases,origins,audit)
    assert len(proofs)==3 and len(views)==5 and fingerprint(corpus)==before
    sources={tuple(v['key']):v for v in frozen['part_views']}
    for key,v in views.items():
        p=v['projection_proof'];o=p['measurement_orientation'];old=sources[tuple(o['source_key'])]
        assert p['complete_native_knowledge']==old['projection_proof']['complete_native_knowledge']
        s,raw=v['frame']['statements'][0],old['frame']['statements'][0]
        assert s['scope']==raw['scope'] and s['attributes']==raw['attributes'] and s['negated']==raw['negated']
        assert [{k:x for k,x in r.items()} for r in s['roles'] if r['role']!='outcome']==[r for r in raw['roles'] if r['role']!='outcome']
        assert not o['full_fact_equivalence'] and not o['scale_equivalence']
        assert all(x in sources for x in map(tuple,p['source_part_keys']))
        assert p['view_frame_sha256']==fingerprint(v['frame'])
    assert any(len(v['projection_proof']['orientation_evidence_ids'])==2 for v in views.values())
    assert {p['source_case']['primary_family'] for p in proofs}=={
        c['primary_family'] for c in cases}


@pytest.mark.parametrize('kind',['quote','anchor','orientation','outcome','source','case','modality','comparator','duplicate'])
def test_forged_or_incompatible_projection_rejected(corpus,kind):
    previous,frozen,maps,origin_audit,cases,audit=deepcopy(corpus);entry=audit['entries'][0]
    if kind=='quote':entry['order_evidence'][0]['text']+='!'
    elif kind=='anchor':entry['anchors'][0]['value']='10'
    elif kind=='orientation':entry['orientation']='higher_is_better'
    elif kind=='outcome':entry['source_outcome']='body weight loss'
    elif kind=='source':entry['source_sha256']='0'*64
    elif kind=='case':entry['case_sha256']='0'*64
    elif kind in {'modality','comparator'}:
        c=next(c for c in cases if c['case_id']==entry['case_id'])
        if kind=='modality':c['result']['frame']['statements'][0]['scope']['modality']='may'
        else:next(r for r in c['result']['frame']['statements'][0]['roles'] if r['role']=='comparator')['value']='unrelated control'
        entry['case_sha256']=fingerprint(c)
    else:audit['entries'].append(deepcopy(entry))
    with pytest.raises(ArticleMapError):project(frozen,maps,cases,validate_origins(maps,origin_audit),audit)


def test_literal_anchor_and_clinical_scale_conflict_are_retained_without_conversion(corpus):
    previous,frozen,maps,origin_audit,cases,audit=corpus
    views,proofs=project(frozen,maps,cases,validate_origins(maps,origin_audit),audit)
    tros=[p for p in proofs if p['case_id'].startswith('tros')];atros=next(p for p in proofs if p['case_id'].startswith('atros'))
    assert all(p['entry']['anchors'][-1]['value']=='6' and p['entry']['scale_caveat_evidence'] for p in tros)
    assert atros['entry']['anchors'][-1]['value']=='5'
    assert all(not p['effect_size_converted'] and not p['scale_equivalence_asserted'] and not p['all_times_or_animals_asserted'] for p in proofs)


def test_no_model_port_or_network_is_needed_for_actual_source_projection(corpus,monkeypatch):
    import socket
    monkeypatch.setattr(socket,'create_connection',lambda *a,**k:pytest.fail('Network/model forbidden'))
    previous,frozen,maps,origin_audit,cases,audit=corpus
    assert project(frozen,maps,cases,validate_origins(maps,origin_audit),audit)[0]


def test_same_ordinal_order_does_not_license_mean_conversion_between_scales(corpus):
    # Строго возрастающая перекодировка сохраняет порядок состояний, но меняет порядок средних групп.
    first=[0,5];second=[3,3];coding={0:0,3:3,5:100}
    assert sum(first)/2<sum(second)/2
    assert sum(coding[x] for x in first)/2>sum(coding[x] for x in second)/2
    previous,frozen,maps,origin_audit,cases,audit=corpus
    _,proofs=project(frozen,maps,cases,validate_origins(maps,origin_audit),audit)
    assert all(not p['scale_equivalence_asserted'] and not p['effect_size_converted'] for p in proofs)

"""Первичные данные не подменяют единицы, фенотипы и удержанные результаты."""
import copy
import json
from pathlib import Path

import pytest

from domain.article_maps import ArticleMapError, fingerprint
from domain.primary_pdf_rates import normalize_rate,transfer_barriers,audit_review
from application.primary_pdf_transfer import prepare_primary_transfer
from infrastructure.primary_pdf_transfer import load_primary_inputs,save_preparation
from infrastructure.cohort_transfer_files import FileCohortTransferInputs
from domain.cohort_transfer import forecast_fold

ROOT=Path(__file__).resolve().parents[2]/'eval/free_prediction/primary-pdf-cohort-v1'
LEGACY=ROOT.parent/'cohort-transfer-v1/prepared/inputs-manifest.json'
SPEC=json.loads((ROOT/'annotation-spec.json').read_text(encoding='utf-8'))


@pytest.fixture(scope='module')
def prepared():
    annotation,evidence,legacy,bindings,identities,texts=load_primary_inputs(ROOT,LEGACY)
    return prepare_primary_transfer(annotation,evidence,legacy,bindings), evidence, identities,texts


@pytest.mark.parametrize('rate',SPEC['rates'],ids=lambda r:r['id'])
def test_all_published_rates_preserve_ci_and_person_time(rate):
    result=normalize_rate(rate)
    from decimal import Decimal
    assert Decimal(result['value'])==Decimal(rate['value'])*1000/rate['per_person_years']
    assert list(map(Decimal,result['interval']))==[Decimal(x)*1000/rate['per_person_years'] for x in rate['interval']]


def test_unchanged_selection_excludes_only_unverified_busse(prepared):
    data=prepared[0]
    assert len(data['observations'])==42 and data['query_count']==30 and len(data['folds'])==6
    assert data['audit']['change_counts']==dict(point_estimate=0,confidence_interval=1,age_bounds=5,phenotype_label=6)
    assert all('Busse' not in o['id'] for o in data['observations'])
    assert len(SPEC['rates'])==49


def test_no_heldout_numbers_abstracts_or_tables_in_input_evidence(prepared):
    result,evidence,*_=prepared
    for fold in result['folds']:
        assert all(o['context']['family_id']!=fold['withheld_family'] for o in fold['training'])
        held=[p for p in fold['evidence'].values() if p['cohort']==fold['withheld_family']]
        assert held and all(p['kind']=='title' and 'Abstract' not in p['text'] for p in held)
        assert all(':title' in k for q in fold['queries'] for k in q['evidence_ids'])
        assert all(set(q)=={'id','context','ages','evidence_ids'} for q in fold['queries'])


def test_offsets_bind_complete_pdf_text_and_unicode(prepared):
    _,evidence,identities,texts=prepared
    for proof in evidence.values():
        assert texts[proof['source_id']][proof['start']:proof['end']]==proof['text']
        assert proof['source_sha256']==identities[proof['source_id']]['layout_sha256']
    assert evidence['larrieu2002:title']['start']>texts['larrieu2002'].index('Brown J')
    assert 'Kertesz' not in evidence['larrieu2002:title']['text']


def test_age_basis_unknown_or_different_does_not_establish_transfer(prepared):
    frames=prepared[0]['frames']
    assert transfer_barriers(frames['Katz-2012:aMCI:85'],frames['Roberts-2012:aMCI:85'])['age_basis']=='different'
    f=frames['Luck-2010:aMCI:85']
    assert transfer_barriers(f,f)['age_basis']=='unknown'


def test_mci_memory_group_is_not_single_domain_amnestic():
    p=SPEC['profiles']['manly2008']
    assert p['extra']['source_MCI_amnestic'].startswith('single memory')
    assert all(r['phenotype'].startswith('MCI-Memory: single and multiple') for r in SPEC['rates'] if r['source_id']=='manly2008' and r['endpoint']=='aMCI')


def test_adjusted_and_observed_rates_are_not_added_as_votes(prepared):
    observed=[r for r in SPEC['rates'] if r['selection']=='alternative']
    assert len(observed)==3
    assert not set(r['id'] for r in observed)&set(o['id'] for o in prepared[0]['observations'])
    assert not SPEC['profiles']['roberts2012']['extra']['crude_reconstruction_allowed']


def test_upper_age_limits_and_ci_are_from_primary_tables(prepared):
    data={o['id']:o for o in prepared[0]['observations']}
    assert data['Katz-2012:naMCI:85']['age']==[85,89]
    assert data['Roberts-2012:MCI:85']['age']==[85,89]
    assert data['Katz-2012:naMCI:70']['interval'][1]=='73.00'
    assert data['Caracciolo-2008:aMCI:85']['age']==[85,None]


def test_retrospective_compilation_is_deterministic_and_idempotent(prepared,tmp_path):
    result,evidence,identities,_=prepared
    before=fingerprint(result)
    save_preparation(tmp_path,result,identities,evidence)
    save_preparation(tmp_path,result,identities,evidence)
    read=FileCohortTransferInputs(tmp_path/'prepared/inputs-manifest.json').read_inputs()
    assert read['folds']==result['folds'] and fingerprint(result)==before
    altered=copy.deepcopy(result);altered['manifest']['metadata']['author']='changed'
    with pytest.raises(ArticleMapError):save_preparation(tmp_path,altered,identities,evidence)


def test_reference_composition_change_rejected(prepared):
    rows=prepared[0]['audit']['rows'];legacy={r['id']:r['review'] for r in rows}
    with pytest.raises(ArticleMapError):audit_review(SPEC['rates'][:-1],{**legacy,'extra':next(iter(legacy.values()))},SPEC['quarantined_review_ids'])


@pytest.mark.parametrize('field,value',[('per_person_years',1),('selection','include'),('age',[85,84]),('interval',['0','1']),('value','NaN')])
def test_invalid_or_ambiguous_rates_rejected(field,value):
    r=copy.deepcopy(SPEC['rates'][0]);r[field]=value
    with pytest.raises(ArticleMapError):normalize_rate(r)


def test_primary_pdf_tampering_is_rejected(monkeypatch):
    read=Path.read_bytes
    def changed(path):
        data=read(path)
        return data+b'changed' if path==ROOT/'sources/katz2012/article.pdf' else data
    monkeypatch.setattr(Path,'read_bytes',changed)
    with pytest.raises(ArticleMapError,match='PDF changed'):load_primary_inputs(ROOT,LEGACY)


def test_prediction_uses_no_ai_network_or_store(monkeypatch,prepared):
    import socket
    monkeypatch.setattr(socket,'socket',lambda *a,**k:pytest.fail('network attempted'))
    for fold in prepared[0]['folds']:
        result=forecast_fold(fold)
        assert result['model_calls']==0 and result['query_count']>0
        assert all(p['order'] is None for p in result['predictions']['strict'])

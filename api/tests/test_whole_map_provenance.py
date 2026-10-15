"""Разделение идентичности и чисел не объединяет когорты и не стирает ограничения."""
from copy import deepcopy
import pytest
from domain.article_maps import ArticleMapError
from domain.whole_map_provenance import partition_provenance
from domain.whole_map_forecast import project
from tests.test_whole_map_forecast import corpus, families


def inputs():
    maps = corpus(); records,_,_=project(maps); family=families(maps)
    record=records[('one','K1')]; statement=record['frame']['statements'][0]
    statement['scope']['study_group']='one'
    statement['attributes'] = [
        {'name':'study id','value':'one','unit':None},
        {'name':'cohort id','value':'one','unit':None},
        {'name':'evidence family','value':'one','unit':None},
        {'name':'n','value':'100','unit':'participants'},
        {'name':'species','value':'human','unit':None},
        {'name':'evidence presentation','value':'own_result','unit':None}]
    return records,family


def test_lossless_partition_keeps_numbers_and_cohort_scope():
    records,family=inputs(); original=deepcopy(records)
    output,audit=partition_provenance(records,family)
    assert records == original and len(audit['proofs']) == 1
    proof=audit['proofs'][0]; after=output[('one','K1')]['frame']
    before=records[('one','K1')]['frame']
    assert proof['parent_frame'] == before
    assert after['statements'][0]['scope'] == before['statements'][0]['scope']
    assert after['statements'][0]['roles'] == before['statements'][0]['roles']
    assert {a['name'] for a in after['statements'][0]['attributes']} == {'n','species','evidence presentation'}
    restored=deepcopy(after)
    for item in proof['identifiers']: restored['statements'][item['statement_index']]['attributes'].append(item['attribute'])
    assert sorted(restored['statements'][0]['attributes'],key=lambda a:a['name']) == sorted(before['statements'][0]['attributes'],key=lambda a:a['name'])


def test_source_identity_can_be_partitioned_without_explicit_study_group():
    records,family=inputs()
    statement=records[('one','K1')]['frame']['statements'][0]
    statement['scope']['study_group']=None
    output,audit=partition_provenance(records,family)
    assert len(audit['proofs']) == 1
    assert output[('one','K1')]['frame']['statements'][0]['scope']['study_group'] is None
    assert {a['name'] for a in output[('one','K1')]['frame']['statements'][0]['attributes']} == {
        'n','species','evidence presentation'}


@pytest.mark.parametrize('change', ['family', 'unit', 'scope', 'duplicate'])
def test_unverified_identity_cannot_disappear(change):
    records,family=inputs(); statement=records[('one','K1')]['frame']['statements'][0]
    if change=='family': family['one']='another cohort'
    elif change=='unit': statement['attributes'][0]['unit']='participants'
    elif change=='scope': statement['scope']['study_group']='another study'
    elif change=='duplicate': statement['attributes'].append(deepcopy(statement['attributes'][0]))
    with pytest.raises(ArticleMapError): partition_provenance(records,family)

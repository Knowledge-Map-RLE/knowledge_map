"""Цитирование и возможность не создают независимых первичных наблюдений."""
from domain.empirical_evidence_eligibility import classify


def item(origin=True, modality=None, kind='state', knowledge_kind='result'):
    return {'knowledge_id':'K1','kind':kind,'knowledge_kind':knowledge_kind,
            'semantic_frame':{'statements':[{'modality':modality,'temporal_context':'study follow-up',
                'conditions':['specified cohort'], 'roles':
                [{'role':'evidence_origin','concept_id':'C1'}] if origin else []}]}}


def test_primary_origin_required():
    assert classify(item(), {'C1':'direct observation in this primary study'})['eligible_direct_observation']
    assert not classify(item(False), {})['eligible_direct_observation']
    assert not classify(item(), {'C1':'studies cited by WHICAP introduction'})['eligible_direct_observation']


def test_hypothesis_and_method_do_not_increase_support():
    concepts = {'C1':'direct observation in this primary study'}
    assert not classify(item(modality='possible'), concepts)['eligible_direct_observation']
    assert not classify(item(kind='action'), concepts)['eligible_direct_observation']
    assert not classify(item(knowledge_kind='definition'), concepts)['eligible_direct_observation']


def test_missing_context_blocks_primary_observation():
    row = item()
    row['semantic_frame']['statements'][0]['temporal_context'] = None
    assert 'context_not_explicit' in classify(row, {'C1':'direct observation in this primary study'})['reasons']

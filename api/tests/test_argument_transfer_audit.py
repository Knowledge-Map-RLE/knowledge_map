"""Проверяет новизну требований и неизменяемость фиксированных операторов."""
import copy
import json
from pathlib import Path

import pytest

from domain.argument_reconstruction import reconstruct
from domain.argument_transfer_audit import classify_transfer
from domain.article_maps import ArticleMapError

REQUESTS = Path(__file__).resolve().parents[2]/'eval/question_prediction/il6-plasma-global-v1/withheld-arguments-engineering-v1/sealed/requests.json'


def example(name): return json.loads(REQUESTS.read_text(encoding='utf-8'))[name]


def test_already_explicit_requirement_is_not_new_knowledge():
    q = example('TOOTH-T8')
    result = classify_transfer(q, reconstruct(q))
    assert result['classification'] == 'known_requirement_restatement'
    assert not result['novel_conclusion'] and not result['clinical_forecast']


def test_covariate_interpretation_is_only_new_relative_to_given_observations():
    q = example('Jordanova-J9')
    r = classify_transfer(q, reconstruct(q))
    assert r['classification'] == 'candidate_interpretation' and r['novel_conclusion']
    assert not r['clinical_forecast']


@pytest.mark.parametrize('name', ['TOOTH-T7', 'Taiwan-F2', 'Taiwan-F3'])
def test_abstentions_never_count_as_matches(name):
    q = example(name); r = classify_transfer(q, reconstruct(q))
    assert r == {'classification': 'abstained', 'novel_conclusion': False, 'clinical_forecast': False}


def test_different_operator_response_rejected():
    q = example('TOOTH-T8'); r = reconstruct(q); r['operator'] = 'empirical_result'
    with pytest.raises(ArticleMapError): classify_transfer(q, r)


def test_rule_transfers_to_other_topic_without_using_target_text():
    q = example('TOOTH-T8'); q['facts'][0]['roles'] = {'index': 'blood-risk-index'}
    q['facts'][0]['context'] = 'Health-ABC-other-local-study'
    c = reconstruct(q)['conclusions'][0]
    assert c['roles'] == {'index': 'blood-risk-index'} and c['action_status'] == 'unresolved'
    assert classify_transfer(q, reconstruct(q))['classification'] == 'known_requirement_restatement'


def test_origin_labels_do_not_turn_requirement_into_novel_result():
    q = example('TOOTH-T8'); original = reconstruct(q)['conclusions']
    q['facts'][0]['origin'] = {'knowledge_id': 'opaque-x', 'statement_ids': ['opaque-y']}
    assert reconstruct(q)['conclusions'] == original
    assert not classify_transfer(q, reconstruct(q))['novel_conclusion']

"""Не допускает превращения цитирования, неопределённости и ошибки координат в прогноз."""
import copy

import pytest

from domain.article_maps import ArticleMapError, digest
from domain.author_use_evidence import audit_author_use


def case():
    text = '😀 Observed method.\n\nReferences\nCitation only.'
    sources = {s: {'text': text, 'sha256': digest(text), 'content_end': text.index('References')} for s in ['a', 'b']}
    p = {'start': 2, 'end': 18, 'text': text[2:18], 'offset_encoding': 'unicode_code_points'}
    control = {'id': 'transfer', 'usage_kind': 'method_adoption', 'primary_status': 'confirmed',
        'later_status': 'explicit_use', 'shared_core': ['Same calculation'], 'limitations': [],
        'earlier': {'source_id': 'a', 'available_on': '2010-01-01', 'family': 'first', 'span': p},
        'later': {'source_id': 'b', 'available_on': '2015-01-01', 'family': 'second', 'span': p}}
    return control, sources


def test_verified_method_transfer_is_not_clinical_prediction_or_fact_equivalence():
    c, s = case(); before = copy.deepcopy((c, s)); result = audit_author_use(c, s)
    assert result['accepted_for_author_use_diagnostic'] and result['different_families']
    assert not result['clinical_prediction_established'] and not result['fact_equivalence_established']
    assert not result['expert_validated'] and (c, s) == before


def test_qualified_argument_requires_retained_limits():
    c, s = case(); c.update(usage_kind='argument_use', primary_status='qualified_match', limitations=['Different outcomes; hypothesis only'])
    assert audit_author_use(c, s)['classification'] == 'verified_qualified_argument_use'
    c['limitations'] = []
    with pytest.raises(ArticleMapError, match='limitations'): audit_author_use(c, s)


def test_citation_only_does_not_establish_author_use():
    c, s = case(); c['later_status'] = 'citation_only'
    assert audit_author_use(c, s)['reasons'] == ['author_use_not_explicit']


def test_unconfirmed_primary_premise_stays_uncertain_not_contradicted():
    c, s = case(); c.update(primary_status='unconfirmed', usage_kind='analysis_rationale')
    result = audit_author_use(c, s)
    assert not result['accepted_for_author_use_diagnostic'] and result['classification'] == 'requires_review'
    assert result['reasons'] == ['primary_premise_not_confirmed']


@pytest.mark.parametrize('date', ['2015-01-01', '2016-01-01'])
def test_same_publication_or_future_cannot_supply_prior_knowledge(date):
    c, s = case(); c['earlier']['available_on'] = date
    assert 'not_strictly_earlier' in audit_author_use(c, s)['reasons']


def test_source_hash_and_unicode_offsets_are_checked():
    c, s = case(); s['a']['text'] += 'changed'
    with pytest.raises(ArticleMapError, match='hash'): audit_author_use(c, s)
    c, s = case(); c['earlier']['span'] = {**c['earlier']['span'], 'start': 3}
    with pytest.raises(ArticleMapError, match='Unicode'): audit_author_use(c, s)


def test_bibliography_is_not_primary_argument_evidence():
    c, s = case(); c['earlier']['span'] = {**c['earlier']['span'], 'start': 32, 'end': 40}
    with pytest.raises(ArticleMapError, match='references'): audit_author_use(c, s)


def test_same_family_is_disclosed_and_empty_core_cannot_pass():
    c, s = case(); c['later']['family'] = 'first'
    assert not audit_author_use(c, s)['different_families']
    c['shared_core'] = []
    assert not audit_author_use(c, s)['accepted_for_author_use_diagnostic']

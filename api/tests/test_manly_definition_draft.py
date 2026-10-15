"""Синтетическая проверка логического черновика; не научная валидация WHICAP."""
from copy import deepcopy
from hashlib import sha256

import pytest

from domain.article_maps import ArticleMapError
from tools import author_manly_definition_draft as draft


def synthetic_source(monkeypatch):
    text = 'Synthetic operational class definition. Synthetic subtype definition.'
    digest = sha256(text.encode()).hexdigest()
    monkeypatch.setattr(draft, 'SOURCE_SHA256', digest)
    return {'sha256': digest, 'text': text, 'content_end': len(text),
            'units': [{'id': uid, 'start': 0, 'end': len(text), 'text': text} for uid in ('U23', 'U25')]}


def test_all_six_subtypes_two_criteria_and_necessary_premises(monkeypatch):
    source = synthetic_source(monkeypatch)
    result = draft.build(source)
    assert result['logical_conclusions'] == 12
    assert all(c['proof']['entailed'] and c['proof']['premises_consistent'] for c in result['conclusions'])
    assert all(not a['entailed'] for c in result['conclusions'] for a in c['premise_removal_checks'])
    assert all(c['proof']['existence_conditions'] == [] for c in result['conclusions'])
    assert not result['full_map_created'] and result['empirical_forecasts'] == 0
    assert result['scope_limitation_ru']


def test_provenance_cannot_be_changed_without_source_revision(monkeypatch):
    source = synthetic_source(monkeypatch)
    damaged = deepcopy(source)
    damaged['units'][0]['text'] = 'A different interpretation disguised as a quotation'
    with pytest.raises(ArticleMapError):
        draft.build(damaged)

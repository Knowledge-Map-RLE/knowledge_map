"""Константы из обучения допустимы без изобретения участников другой статьи."""
from copy import deepcopy
from domain.whole_map_forecast import forecast
from tests.test_whole_map_forecast import corpus, families


def with_head_constant(receiving_has_symbol):
    maps = corpus()
    for m in maps[:2]:
        m['graph']['concepts'].append({'id': 'C3', 'display_text': 'omega', 'aliases': []})
        m['graph']['knowledge'][-1]['semantic_frame']['statements'][0]['roles'].append(
            {'role': 'outcome_type', 'concept_id': 'C3', 'knowledge_id': None})
    if receiving_has_symbol:
        m = maps[-1]
        m['graph']['concepts'].append({'id': 'C3', 'display_text': 'omega', 'aliases': []})
        # Понятие присутствует в отдельном знании, а не в непосредственных входах.
        k = deepcopy(m['graph']['knowledge'][0])
        k['knowledge_id'] = 'K3'
        s = k['semantic_frame']['statements'][0]
        s['statement_id'] = 'S3'
        s['predicate'] = 'mentions'
        s['roles'] = [{'role': 'subject', 'concept_id': 'C3', 'knowledge_id': None}]
        m['graph']['knowledge'].append(k)
        m['graph']['nodes'].append({'id': 'B3', 'knowledge_id': 'K3'})
    return maps


def test_known_training_constant_does_not_require_a_head_variable():
    maps = with_head_constant(True)
    result = forecast(maps, families(maps))
    assert result['rules']
    assert result['predictions']['same_rules_without_dependencies']
    assert all(not p['logical_entailment'] for p in result['predictions']['same_rules_without_dependencies'])


def test_constant_absent_from_receiving_article_cannot_be_invented():
    maps = with_head_constant(False)
    result = forecast(maps, families(maps))
    assert result['rules'] and not result['predictions']['same_rules_without_dependencies']
    assert result['diagnostics']['same_rules_without_dependencies']['rejected']['head_constant_not_grounded_in_receiving_source']


def test_different_head_constants_do_not_merge_into_a_supported_rule():
    maps = with_head_constant(True)
    maps[1]['graph']['concepts'][-1]['display_text'] = 'another outcome'
    assert not forecast(maps, families(maps))['rules']
